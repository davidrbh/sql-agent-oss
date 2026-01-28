/**
 * @file index.ts
 * @description Servidor MCP (Model Context Protocol) Sidecar para MySQL.
 * Este servicio actúa como un puente seguro entre el agente de IA y la base de datos,
 * exponiendo herramientas para la ejecución de consultas SQL validadas.
 * 
 * Basado en Fastify para el transporte de red y @modelcontextprotocol/sdk para la lógica del protocolo.
 */

import "dotenv/config";

import cors from "@fastify/cors";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import Fastify, { FastifyReply, FastifyRequest } from "fastify";
import mysql from "mysql2/promise";

/**
 * Instancia del servidor Fastify.
 * Se encarga de gestionar las conexiones HTTP y los eventos SSE.
 */
const fastify = Fastify({
  logger: true,
});

/**
 * Pool de conexiones a MySQL.
 * Configurado fuera del manejador para permitir persistencia y reutilización de conexiones.
 * Utiliza variables de entorno para la configuración.
 */
const pool = mysql.createPool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  waitForConnections: true,
  connectionLimit: 30, // Límite seguro para DB remota
  queueLimit: 0,        // Sin límite de cola para no rechazar peticiones
  enableKeepAlive: true,
  keepAliveInitialDelay: 10000,
  connectTimeout: 30000, // 30s para lidiar con latencia de red
  idleTimeout: 60000,    // Mantener conexiones inactivas por 1 min
});

/**
 * Inicializa y arranca el ecosistema del Sidecar MCP.
 * Configura CORS, parsers personalizados, el servidor MCP y las rutas de Fastify.
 * 
 * @async
 * @function start
 * @returns {Promise<void>}
 */
const start = async () => {
  // Registrar el plugin de CORS
  await fastify.register(cors, {
    origin: true, // Permitir todos los orígenes para simplicidad en desarrollo
  });

  /**
   * Bypass al parsing JSON por defecto.
   * Esto permite que el SDK de MCP consuma el flujo (stream) crudo de la petición,
   * delegando el manejo de mensajes JSON-RPC al protocolo.
   */
  fastify.addContentTypeParser("application/json", (req, payload, done) => {
    done(null, payload);
  });

  /**
   * Inicialización del servidor MCP.
   * Define las capacidades y la identidad del servidor.
   */
  const server = new Server(
    {
      name: "mysql-sidecar",
      version: "1.0.0",
    },
    {
      capabilities: {
        tools: {},
      },
    },
  );

  /**
   * Manejador para el descubrimiento de herramientas.
   * Expone la lista de funciones disponibles que el agente de IA puede invocar.
   */
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    await Promise.resolve();
    return {
      tools: [
        {
          name: "query",
          description: "Ejecuta una consulta SQL segura (Solo LECTURA)",
          inputSchema: {
            type: "object",
            properties: {
              sql: { type: "string" },
            },
            required: ["sql"],
          },
        },
      ],
    };
  });

  /**
   * Manejador para la ejecución de herramientas.
   * Implementa la lógica de negocio para la herramienta 'query'.
   * Incluye una capa de seguridad crítica que valida operaciones de solo lectura.
   */
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    if (request.params.name === "query") {
      // Extraer el argumento SQL, manejando posibles arrays o strings
      const sql = Array.isArray(request.params.arguments?.sql)
        ? request.params.arguments?.sql[0]
        : request.params.arguments?.sql;

      if (typeof sql !== "string") {
        throw new TypeError("Argumento SQL inválido");
      }

      /**
       * --- CAPA DE SEGURIDAD V4 (Defensa en Profundidad) ---
       * Aunque el Host ya valida, el Sidecar es la última línea de defensa.
       * Rechazamos cualquier operación que no sea estrictamente de lectura.
       */
      const cleanSql = sql.replace(/\/\*[\s\S]*?\*\/|--.*$/gm, "").trim().toUpperCase();
      const safeKeywords = ["SELECT", "DESCRIBE", "DESC", "SHOW", "EXPLAIN", "WITH"];
      const isReadOnly = safeKeywords.some(kw => cleanSql.startsWith(kw));

      if (!isReadOnly) {
         return {
          isError: true,
          content: [
            { type: "text", text: `⛔ SEGURIDAD: El Sidecar ha bloqueado esta consulta. Solo se permiten operaciones de lectura (SELECT/DESCRIBE/SHOW/WITH/EXPLAIN).` },
          ],
        };
      }

      try {
        // 2. EJECUCIÓN REAL
        fastify.log.info({ sql }, "Ejecutando consulta SQL");
        const [rows] = await pool.execute(sql);


        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(rows, null, 2),
            },
          ],
        };
      } catch (error) {
        return {
          isError: true,
          content: [
            { type: "text", text: `Error MySQL: ${(error as Error).message}` },
          ],
        };
      }
    }
    throw new Error("Herramienta no encontrada");
  });

  /**
   * Mapa de sesiones activas.
   * Asocia IDs de sesión con sus respectivos transportes SSE.
   */
  const transports = new Map<string, SSEServerTransport>();

  /**
   * Ruta de salud (Health Check).
   */
  fastify.get("/health", async () => {
    await Promise.resolve();
    return { status: "ok" };
  });

  /**
   * Endpoint principal para el establecimiento de conexiones SSE.
   * Inicia el transporte SSE y vincula el servidor MCP a la nueva sesión.
   */
  fastify.get("/sse", async (req: FastifyRequest, reply: FastifyReply) => {
    reply.hijack(); // Tomar control manual de la respuesta para SSE

    const transport = new SSEServerTransport("/messages", reply.raw);
    const sessionId = transport.sessionId;
    transports.set(sessionId, transport);

    // Conectar el servidor MCP al transporte
    await server.connect(transport);

    // Limpieza al cerrar la conexión
    req.raw.on("close", () => {
      transports.delete(sessionId);
    });
  });

  /**
   * Endpoint para la recepción de mensajes JSON-RPC.
   * Enruta los mensajes POST al transporte SSE correspondiente basado en el sessionId.
   */
  fastify.post(
    "/messages",
    async (req: FastifyRequest, reply: FastifyReply) => {
      const sessionId = (req.query as { sessionId?: string }).sessionId;

      if (!sessionId || !transports.has(sessionId)) {
        reply.status(404).send({ error: "Sesión no encontrada" });
        return;
      }

      const transport = transports.get(sessionId);
      if (transport) {
        reply.hijack();
        // @ts-expect-error - req.body es tratado como stream por el parser personalizado
        await transport.handlePostMessage(req.body, reply.raw);
      }
    },
  );

  try {
    /**
     * Arranca la escucha del servidor Fastify.
     */
    await fastify.listen({ port: 3002, host: "0.0.0.0" });
  } catch (error) {
    fastify.log.error(error);
    process.exit(1);
  }
};

// Ejecutar el inicio del servidor
void start();
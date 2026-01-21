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
// import { z } from "zod";

const fastify = Fastify({
  logger: true,
});

// 1. Connection Pool (Outside handler to be persistent)
const pool = mysql.createPool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0,
});

const start = async () => {
  await fastify.register(cors, {
    origin: true, // Allow all origins for dev simplicity, tune for prod
  });

  // Bypass default JSON parsing so MCP SDK can consume the raw stream
  // "payload" here is the incoming stream
  fastify.addContentTypeParser("application/json", (req, payload, done) => {
    done(null, payload);
  });

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

  // Define tools
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    // Simulated async operation
    await Promise.resolve();
    return {
      tools: [
        {
          name: "query",
          description: "Execute a SQL query",
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

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    if (request.params.name === "query") {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
      const sql = Array.isArray(request.params.arguments?.sql)
        ? request.params.arguments?.sql[0]
        : request.params.arguments?.sql;

      if (typeof sql !== "string") {
        throw new TypeError("Invalid SQL argument");
      }

      try {
        // 2. REAL EXECUTION (Replaces Mock)
        const [rows] = await pool.execute(sql);

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(rows, null, 2), // Return real data as JSON
            },
          ],
        };
      } catch (error) {
        return {
          isError: true,
          content: [
            { type: "text", text: `MySQL Error: ${(error as Error).message}` },
          ],
        };
      }
    }
    throw new Error("Tool not found");
  });

  // Map of sessionId -> Transport
  const transports = new Map<string, SSEServerTransport>();

  fastify.get("/health", async () => {
    // Simulated async health check
    await Promise.resolve();
    return { status: "ok" };
  });

  fastify.get("/sse", async (req: FastifyRequest, reply: FastifyReply) => {
    // Delegate response handling to MCP SDK
    reply.hijack();

    const transport = new SSEServerTransport("/messages", reply.raw);

    const sessionId = transport.sessionId;
    transports.set(sessionId, transport);

    // We need to keep the connection open.
    await server.connect(transport);

    // Cleanup on close
    req.raw.on("close", () => {
      transports.delete(sessionId);
    });
  });

  fastify.post(
    "/messages",
    async (req: FastifyRequest, reply: FastifyReply) => {
      const sessionId = (req.query as { sessionId?: string }).sessionId;

      if (!sessionId || !transports.has(sessionId)) {
        reply.status(404).send({ error: "Session not found" });
        return;
      }

      const transport = transports.get(sessionId);
      if (transport) {
        // Delegate response handling to MCP SDK
        reply.hijack();

        // req.body is now the raw stream because of our custom parser
        // @ts-expect-error - req.body is raw stream
        await transport.handlePostMessage(req.body, reply.raw);
      }
    },
  );

  try {
    await fastify.listen({ port: 3002, host: "0.0.0.0" });
  } catch (error) {
    fastify.log.error(error);
    // eslint-disable-next-line unicorn/no-process-exit
    process.exit(1);
  }
};

void start();

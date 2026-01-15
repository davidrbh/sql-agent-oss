import Fastify, { FastifyRequest, FastifyReply } from "fastify";
import cors from "@fastify/cors";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

const fastify = Fastify({
  logger: true,
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
    }
  );

  // Define tools
  server.setRequestHandler(ListToolsRequestSchema, async () => {
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
      const sql = Array.isArray(request.params.arguments?.sql)
        ? request.params.arguments?.sql[0]
        : request.params.arguments?.sql;

      if (typeof sql !== "string") {
        throw new Error("Invalid SQL argument");
      }

      // In a real implementation, we'd connect to MySQL here
      return {
        content: [{ type: "text", text: `Executed: ${sql}` }],
      };
    }
    throw new Error("Tool not found");
  });

  // Map of sessionId -> Transport
  const transports = new Map<string, SSEServerTransport>();

  fastify.get("/health", async (req, reply) => {
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
        // @ts-ignore
        await transport.handlePostMessage(req.body, reply.raw);
      }
    }
  );

  try {
    await fastify.listen({ port: 3000, host: "0.0.0.0" });
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();

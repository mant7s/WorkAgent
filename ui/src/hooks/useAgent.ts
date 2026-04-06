import { useState, useCallback } from "react";
import type {
  AgentConfig,
  AgentResult,
  AgentStatus,
  Tool,
} from "@/types/agent";

const API_BASE_URL = "http://localhost:8000";

export function useAgent() {
  const [status, setStatus] = useState<AgentStatus>({ status: "idle" });
  const [result, setResult] = useState<AgentResult | null>(null);
  const [loading, setLoading] = useState(false);

  const runAgent = useCallback(
    async (query: string, config?: Partial<AgentConfig>) => {
      setLoading(true);
      setStatus({ status: "running", message: "Agent is thinking..." });
      setResult(null);

      try {
        const response = await fetch(`${API_BASE_URL}/api/agent/run`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            model: config?.model || "gpt-4o-mini",
            messages: [{ role: "user", content: query }],
            temperature: config?.temperature || 0.7,
            max_iterations: config?.max_iterations || 10,
            token_budget: config?.token_budget || 10000,
            tools: config?.tools,
          }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        setResult({
          answer: data.content,
          iterations: data.iterations,
          tokenUsage: data.usage,
          executionTime: data.execution_time,
          tool_calls: data.tool_calls?.map((tc: { name: string; arguments: Record<string, unknown>; result?: unknown }) => ({
            name: tc.name,
            arguments: tc.arguments,
            result: tc.result,
          })),
          thoughts: data.tool_calls?.map((tc: { name: string; arguments: Record<string, unknown> }, idx: number) => ({
            step: idx + 1,
            thought: `调用工具: ${tc.name}`,
            action: tc.name,
            observation: JSON.stringify(tc.arguments),
          })),
        });
        setStatus({ status: "completed", message: "Task completed" });
      } catch (error) {
        setStatus({
          status: "failed",
          message:
            error instanceof Error ? error.message : "Failed to run agent",
        });
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const getTools = useCallback(async (): Promise<Tool[]> => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/tools`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      return data.tools || [];
    } catch (error) {
      console.error("Failed to fetch tools:", error);
      return [];
    }
  }, []);

  const getHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      return response.ok;
    } catch {
      return false;
    }
  }, []);

  return {
    status,
    result,
    loading,
    runAgent,
    getTools,
    getHealth,
  };
}

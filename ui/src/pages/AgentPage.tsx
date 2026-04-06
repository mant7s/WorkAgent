import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useAgent } from "@/hooks/useAgent";
import type { Tool } from "@/types/agent";

export function AgentPage() {
  const [query, setQuery] = useState("");
  const [tools, setTools] = useState<Tool[]>([]);
  const { status, result, loading, runAgent, getTools, getHealth } = useAgent();
  const [isHealthy, setIsHealthy] = useState(false);

  useEffect(() => {
    getTools().then(setTools);
    getHealth().then(setIsHealthy);
  }, [getTools, getHealth]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    await runAgent(query);
  };

  const getStatusColor = () => {
    switch (status.status) {
      case "running":
        return "bg-yellow-500";
      case "completed":
        return "bg-green-500";
      case "failed":
        return "bg-red-500";
      default:
        return "bg-gray-500";
    }
  };

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">WorkAgent</h1>
            <p className="text-muted-foreground">
              轻量级 AI Agent 框架可视化界面
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Backend:</span>
            <Badge variant={isHealthy ? "default" : "destructive"}>
              {isHealthy ? "Connected" : "Disconnected"}
            </Badge>
          </div>
        </div>

        {/* Input Section */}
        <Card>
          <CardHeader>
            <CardTitle>任务输入</CardTitle>
            <CardDescription>
              输入你的问题或任务，Agent 将自动选择合适的工具完成
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <Textarea
                placeholder="例如：计算 15 * 23 + 47，或者搜索今天北京的天气..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                rows={4}
                disabled={loading}
              />
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`h-2 w-2 rounded-full ${getStatusColor()}`} />
                  <span className="text-sm text-muted-foreground">
                    {status.message || "Ready"}
                  </span>
                </div>
                <Button type="submit" disabled={loading || !query.trim()}>
                  {loading ? "运行中..." : "运行 Agent"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Tools Section */}
        <Card>
          <CardHeader>
            <CardTitle>可用工具</CardTitle>
            <CardDescription>Agent 可以调用的工具列表</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {tools.map((tool) => (
                <Badge
                  key={tool.name}
                  variant={tool.dangerous ? "destructive" : "secondary"}
                >
                  {tool.name}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Result Section */}
        {result && (
          <Card>
            <CardHeader>
              <CardTitle>执行结果</CardTitle>
              <CardDescription>
                迭代次数: {result.iterations ?? 0} | Token 使用: {" "}
                {result.tokenUsage?.total_tokens ?? 0} | 执行时间: {" "}
                {(result.executionTime ?? 0).toFixed(2)}s
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg bg-muted p-4">
                <h3 className="font-semibold mb-2">最终答案</h3>
                <p className="whitespace-pre-wrap">{result.answer}</p>
              </div>

              {result.thoughts && result.thoughts.length > 0 && (
                <div className="space-y-2">
                  <h3 className="font-semibold">思考过程</h3>
                  {result.thoughts.map((thought, index) => (
                    <div
                      key={index}
                      className="rounded-lg border p-3 text-sm"
                    >
                      <p className="text-muted-foreground mb-2">
                        Step {thought.step ?? index + 1}
                      </p>
                      {thought.thought && (
                        <p className="mb-2">{thought.thought}</p>
                      )}
                      {thought.action && (
                        <div className="rounded bg-muted px-2 py-1 font-mono text-xs">
                          {thought.action}(
                          {thought.observation ? JSON.stringify(thought.observation) : ""})
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

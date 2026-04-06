export interface AgentConfig {
  model: string
  temperature: number
  max_iterations: number
  token_budget: number
  tools?: string[]
}

export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface Thought {
  step: number
  thought: string
  action?: string
  observation?: string
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  result?: unknown
}

export interface AgentResult {
  answer: string
  thoughts?: Thought[]
  tool_calls?: ToolCall[]
  tokenUsage?: TokenUsage
  iterations: number
  executionTime: number
}

export interface AgentStatus {
  status: "idle" | "running" | "completed" | "failed"
  message?: string
}

export interface Tool {
  name: string
  description: string
  category: string
  dangerous?: boolean
  parameters?: Record<string, unknown>
}

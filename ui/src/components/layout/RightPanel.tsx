import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Wrench,
  Clock,
  Calculator,
  Search,
  CloudSun,
  Activity,
  Loader2,
  AlertCircle,
  Cpu,
  CheckCircle2,
  XCircle,
} from "lucide-react"
import type { Tool } from "@/types/agent"

interface RightPanelProps {
  className?: string
  onClose?: () => void
}

interface HealthStatus {
  status: string
  version: string
  providers: string[]
  tools: string[]
}

const getToolIcon = (toolName: string) => {
  const iconMap: Record<string, { icon: React.ElementType; color: string; bg: string }> = {
    calculator: { icon: Calculator, color: "text-blue-600", bg: "bg-blue-50" },
    web_search: { icon: Search, color: "text-emerald-600", bg: "bg-emerald-50" },
    get_current_weather: { icon: CloudSun, color: "text-amber-600", bg: "bg-amber-50" },
    get_current_time: { icon: Clock, color: "text-violet-600", bg: "bg-violet-50" },
  }
  return iconMap[toolName] || { icon: Wrench, color: "text-gray-600", bg: "bg-gray-50" }
}

const API_BASE_URL = "http://localhost:8000"

export function RightPanel({ className, onClose }: RightPanelProps) {
  const [tools, setTools] = useState<Tool[]>([])
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        setError(null)

        const [toolsRes, healthRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/tools`),
          fetch(`${API_BASE_URL}/health`),
        ])

        if (!toolsRes.ok) {
          throw new Error(`Failed to fetch tools: ${toolsRes.status}`)
        }
        if (!healthRes.ok) {
          throw new Error(`Failed to fetch health: ${healthRes.status}`)
        }

        const toolsData = await toolsRes.json()
        const healthData = await healthRes.json()

        setTools(toolsData.tools || [])
        setHealth(healthData)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch data")
      } finally {
        setLoading(false)
      }
    }

    fetchData()

    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [])

  const isConnected = health?.status === "healthy"

  return (
    <aside
      className={cn(
        "flex flex-col h-full bg-gray-50/50",
        className
      )}
    >
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          {/* Status Card */}
          <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100">
            <div className="flex items-center gap-3">
              <div className={cn(
                "flex h-12 w-12 items-center justify-center rounded-xl shrink-0",
                isConnected ? "bg-emerald-50" : "bg-red-50"
              )}>
                {loading ? (
                  <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
                ) : isConnected ? (
                  <CheckCircle2 className="h-6 w-6 text-emerald-500" />
                ) : (
                  <XCircle className="h-6 w-6 text-red-500" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-gray-900">
                  {loading ? "连接中..." : isConnected ? "运行正常" : "连接失败"}
                </p>
                <div className="flex items-center gap-2 text-sm text-gray-500 mt-0.5">
                  <span>v{health?.version || "0.0.0"}</span>
                  <span className="text-gray-300">·</span>
                  <span>{tools.length} 个工具</span>
                </div>
              </div>
            </div>
          </div>

          {/* Tools Section */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
              <h3 className="font-semibold text-gray-900">可用工具</h3>
              {loading && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
            </div>
            
            {error ? (
              <div className="p-4 text-sm text-red-600 bg-red-50">
                {error}
              </div>
            ) : tools.length === 0 && !loading ? (
              <div className="p-8 text-sm text-gray-400 text-center">
                暂无可用工具
              </div>
            ) : (
              <div className="divide-y divide-gray-50">
                {tools.map((tool) => {
                  const { icon: Icon, color, bg } = getToolIcon(tool.name)
                  return (
                    <div
                      key={tool.name}
                      className="flex items-center gap-3 p-3 hover:bg-gray-50/50 transition-colors cursor-pointer"
                      title={tool.description}
                    >
                      <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg shrink-0", bg)}>
                        <Icon className={cn("h-4 w-4", color)} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">{tool.name}</p>
                        <p className="text-xs text-gray-400 capitalize">{tool.category}</p>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Providers Section */}
          {health?.providers && health.providers.length > 0 && (
            <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100">
              <h3 className="font-semibold text-gray-900 mb-3">模型提供商</h3>
              <div className="flex flex-wrap gap-2">
                {health.providers.map((provider) => (
                  <span
                    key={provider}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-50 text-sm font-medium text-gray-700 border border-gray-100"
                  >
                    <Cpu className="h-3.5 w-3.5 text-gray-400" />
                    {provider}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
    </aside>
  )
}

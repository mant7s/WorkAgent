import { useState, useRef, useEffect } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import {
  Sheet,
  SheetContent,
  SheetTrigger,
} from "@/components/ui/sheet"
import { RightPanel } from "@/components/layout/RightPanel"
import { useAgent } from "@/hooks/useAgent"
import {
  Send,
  Loader2,
  Bot,
  User,
  Sparkles,
  PanelRight,
} from "lucide-react"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
}

export function ChatPage() {
  const [input, setInput] = useState("")
  const [messages, setMessages] = useState<Message[]>([])
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const { status, result, loading, runAgent } = useAgent()

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, result])

  // Add assistant message when result is received
  useEffect(() => {
    if (result && status.status === "completed") {
      const assistantMessage: Message = {
        id: Date.now().toString(),
        role: "assistant",
        content: result.answer,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, assistantMessage])
    }
  }, [result, status.status])

  const handleSend = async () => {
    if (!input.trim() || loading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInput("")

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
    }

    await runAgent(userMessage.content)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
    // Shift+Enter will naturally insert a new line
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)

    // Auto-resize textarea
    const textarea = e.target
    textarea.style.height = "auto"
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
  }

  const getStatusBadge = () => {
    switch (status.status) {
      case "running":
        return (
          <Badge
            variant="secondary"
            className="bg-amber-500/10 text-amber-600 hover:bg-amber-500/20"
          >
            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
            运行中
          </Badge>
        )
      case "completed":
        return (
          <Badge
            variant="secondary"
            className="bg-green-500/10 text-green-600 hover:bg-green-500/20"
          >
            已完成
          </Badge>
        )
      case "failed":
        return (
          <Badge
            variant="secondary"
            className="bg-destructive/10 text-destructive hover:bg-destructive/20"
          >
            失败
          </Badge>
        )
      default:
        return (
          <Badge
            variant="secondary"
            className="bg-muted text-muted-foreground"
          >
            空闲
          </Badge>
        )
    }
  }

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header */}
      <header className="flex h-16 items-center justify-between border-b px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
            <Bot className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">AI Agent</h1>
            <p className="text-xs text-muted-foreground">
              智能助手，随时为您服务
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {getStatusBadge()}
          <Sheet open={isRightPanelOpen} onOpenChange={setIsRightPanelOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="h-9 w-9">
                <PanelRight className="h-5 w-5" />
                <span className="sr-only">详情</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-80 p-0">
              <RightPanel onClose={() => setIsRightPanelOpen(false)} />
            </SheetContent>
          </Sheet>
        </div>
      </header>

      {/* Messages Area */}
      <div className="flex-1 overflow-hidden">
        {messages.length === 0 ? (
          // Empty State
          <div className="flex h-full flex-col items-center justify-center px-6">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 mb-6">
              <Sparkles className="h-8 w-8 text-primary" />
            </div>
            <h2 className="text-2xl font-semibold tracking-tight mb-2">
              有什么可以帮您的？
            </h2>
            <p className="text-muted-foreground text-center max-w-md mb-8">
              我是您的 AI 助手，可以回答问题、执行任务、调用工具等。
              在下方输入框中开始对话吧。
            </p>
            <div className="flex flex-wrap justify-center gap-2 max-w-lg">
              {["查询天气", "计算数学", "搜索信息", "代码帮助"].map(
                (suggestion) => (
                  <Button
                    key={suggestion}
                    variant="outline"
                    size="sm"
                    className="rounded-full"
                    onClick={() => {
                      setInput(suggestion)
                      textareaRef.current?.focus()
                    }}
                  >
                    {suggestion}
                  </Button>
                )
              )}
            </div>
          </div>
        ) : (
          // Message List
          <div className="h-full overflow-y-auto px-6 py-6">
            <div className="mx-auto max-w-3xl space-y-6">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={cn(
                    "flex gap-4",
                    message.role === "user" ? "flex-row-reverse" : "flex-row"
                  )}
                >
                  <div
                    className={cn(
                      "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                      message.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-primary/10 text-primary"
                    )}
                  >
                    {message.role === "user" ? (
                      <User className="h-4 w-4" />
                    ) : (
                      <Bot className="h-4 w-4" />
                    )}
                  </div>
                  <div
                    className={cn(
                      "flex max-w-[calc(100%-3rem)] flex-col",
                      message.role === "user" ? "items-end" : "items-start"
                    )}
                  >
                    <div
                      className={cn(
                        "rounded-2xl px-4 py-3 text-sm",
                        message.role === "user"
                          ? "bg-primary text-primary-foreground rounded-br-md"
                          : "bg-muted rounded-bl-md"
                      )}
                    >
                      {message.content}
                    </div>
                    <span className="mt-1 text-xs text-muted-foreground">
                      {message.timestamp.toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex gap-4">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="flex items-center gap-2 rounded-2xl rounded-bl-md bg-muted px-4 py-3">
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">
                      {status.message || "思考中..."}
                    </span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}
      </div>

      {/* Input Area - Floating Style */}
      <div className="bg-background px-6 pb-6 pt-2">
        <div className="mx-auto max-w-3xl">
          <div className="relative group">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="输入消息..."
              className="min-h-[56px] max-h-[200px] w-full resize-none rounded-2xl border-0 bg-muted/40 py-4 pl-4 pr-14 text-sm shadow-none transition-all duration-200 ease-out placeholder:text-muted-foreground/50 hover:bg-muted/60 focus-visible:bg-background focus-visible:ring-1 focus-visible:ring-primary/20 focus-visible:shadow-[0_0_0_4px_rgba(0,0,0,0.02)]"
              rows={1}
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || loading}
              size="icon"
              className="absolute right-2 bottom-2 h-10 w-10 rounded-xl opacity-60 transition-all duration-200 group-hover:opacity-100 hover:scale-105 active:scale-95 disabled:opacity-30"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <p className="mt-3 text-center text-xs text-muted-foreground/60">
            按 Enter 发送，Shift+Enter 换行
          </p>
        </div>
      </div>
    </div>
  )
}

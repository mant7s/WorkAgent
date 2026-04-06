import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { MessageSquare, Activity, Settings, Plus, Bot } from "lucide-react"
import { cva } from "class-variance-authority"

interface SidebarProps {
  className?: string
}

const navItems = [
  { icon: MessageSquare, label: "对话测试", path: "/", active: true },
  { icon: Activity, label: "执行日志", path: "/logs", active: false },
  { icon: Settings, label: "系统设置", path: "/settings", active: false },
]

const navItemVariants = cva(
  "w-full justify-start gap-3 h-9 px-3 text-sm font-medium transition-all duration-200 rounded-lg",
  {
    variants: {
      active: {
        true: "bg-muted text-foreground font-semibold",
        false: "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
      },
    },
    defaultVariants: {
      active: false,
    },
  }
)

export function Sidebar({ className }: SidebarProps) {
  return (
    <TooltipProvider delayDuration={0}>
      <aside
        className={cn("flex flex-col bg-background", className)}
      >
        {/* Logo */}
        <div className="flex h-14 items-center gap-3 px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Bot className="h-4 w-4" />
          </div>
          <span className="text-base font-semibold tracking-tight">WorkAgent</span>
        </div>

        {/* New Agent Button */}
        <div className="px-3 pb-3">
          <Button
            variant="outline"
            size="sm"
            className="w-full justify-start gap-2 h-9 text-sm border-dashed border-muted-foreground/30 text-muted-foreground hover:border-muted-foreground/50 hover:text-foreground hover:bg-muted/50"
          >
            <Plus className="h-4 w-4" />
            新建 Agent
          </Button>
        </div>

        {/* Navigation */}
        <ScrollArea className="flex-1 px-3">
          <nav className="space-y-0.5">
            {navItems.map((item) => (
              <Tooltip key={item.path}>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    className={cn(navItemVariants({ active: item.active }))}
                  >
                    <item.icon className="h-4 w-4" />
                    {item.label}
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">
                  {item.label}
                </TooltipContent>
              </Tooltip>
            ))}
          </nav>
        </ScrollArea>

        {/* User Section */}
        <div className="p-3">
          <div className="flex items-center gap-2.5 p-2 rounded-lg bg-muted/50 hover:bg-muted transition-colors cursor-pointer">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-background border">
              <span className="text-xs font-medium">U</span>
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-medium">User</span>
              <span className="text-[11px] text-muted-foreground">user@example.com</span>
            </div>
          </div>
        </div>
      </aside>
    </TooltipProvider>
  )
}

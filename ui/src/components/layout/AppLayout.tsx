import { cn } from "@/lib/utils"
import { Sidebar } from "@/components/layout/Sidebar"

interface AppLayoutProps {
  children: React.ReactNode
  className?: string
}

export function AppLayout({ children, className }: AppLayoutProps) {
  return (
    <div className={cn("flex h-screen w-full overflow-hidden bg-background", className)}>
      {/* Sidebar - Soybean Admin style */}
      <div className="flex w-64 flex-col border-r border-[#f0f0f0] dark:border-[#2d2d2d]">
        <Sidebar className="flex-1" />
      </div>
      
      {/* Main content */}
      <main className="flex flex-1 flex-col min-w-0">
        {children}
      </main>
    </div>
  )
}

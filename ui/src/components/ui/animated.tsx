import { cn } from "@/lib/utils"
import { forwardRef } from "react"

// Animated container with stagger children
interface AnimatedContainerProps {
  children: React.ReactNode
  className?: string
  stagger?: number
}

export function AnimatedContainer({ children, className, stagger = 50 }: AnimatedContainerProps) {
  return (
    <div className={cn("animate-container", className)} style={{ "--stagger": `${stagger}ms` } as React.CSSProperties}>
      {children}
    </div>
  )
}

// Fade in up animation wrapper
interface FadeInUpProps {
  children: React.ReactNode
  className?: string
  delay?: number
}

export function FadeInUp({ children, className, delay = 0 }: FadeInUpProps) {
  return (
    <div
      className={cn("animate-fade-in-up", className)}
      style={{ animationDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}

// Scale in animation wrapper
interface ScaleInProps {
  children: React.ReactNode
  className?: string
  delay?: number
}

export function ScaleIn({ children, className, delay = 0 }: ScaleInProps) {
  return (
    <div
      className={cn("animate-scale-in", className)}
      style={{ animationDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}

// Slide in from right
interface SlideInRightProps {
  children: React.ReactNode
  className?: string
  delay?: number
}

export function SlideInRight({ children, className, delay = 0 }: SlideInRightProps) {
  return (
    <div
      className={cn("animate-slide-in-right", className)}
      style={{ animationDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}

// Pulse dot for status indicators
interface PulseDotProps {
  className?: string
  color?: "success" | "error" | "warning" | "info" | "brand"
}

const colorMap = {
  success: "bg-success",
  error: "bg-error",
  warning: "bg-warning",
  info: "bg-info",
  brand: "bg-brand-500",
}

export function PulseDot({ className, color = "brand" }: PulseDotProps) {
  return (
    <span className={cn("relative flex h-2 w-2", className)}>
      <span className={cn("animate-ping absolute inline-flex h-full w-full rounded-full opacity-75", colorMap[color])}></span>
      <span className={cn("relative inline-flex rounded-full h-2 w-2", colorMap[color])}></span>
    </span>
  )
}

// Shimmer loading effect
interface ShimmerProps {
  className?: string
}

export function Shimmer({ className }: ShimmerProps) {
  return (
    <div className={cn("relative overflow-hidden bg-bg-tertiary rounded-xl", className)}>
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/20 to-transparent" />
    </div>
  )
}

// Hover lift effect wrapper
interface HoverLiftProps {
  children: React.ReactNode
  className?: string
}

export const HoverLift = forwardRef<HTMLDivElement, HoverLiftProps>(
  ({ children, className }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "transition-all duration-250 ease-out",
          "hover:-translate-y-0.5 hover:shadow-md",
          "active:translate-y-0 active:shadow-sm",
          className
        )}
      >
        {children}
      </div>
    )
  }
)
HoverLift.displayName = "HoverLift"

// Magnetic button effect (simplified)
interface MagneticButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode
  className?: string
}

export const MagneticButton = forwardRef<HTMLButtonElement, MagneticButtonProps>(
  ({ children, className, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "relative transition-transform duration-150 ease-out",
          "hover:scale-105 active:scale-95",
          className
        )}
        {...props}
      >
        {children}
      </button>
    )
  }
)
MagneticButton.displayName = "MagneticButton"

// Typing indicator for AI
interface TypingIndicatorProps {
  className?: string
}

export function TypingIndicator({ className }: TypingIndicatorProps) {
  return (
    <div className={cn("flex items-center gap-1 px-1", className)}>
      <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-bounce" style={{ animationDelay: "0ms" }} />
      <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-bounce" style={{ animationDelay: "150ms" }} />
      <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-bounce" style={{ animationDelay: "300ms" }} />
    </div>
  )
}

// Glow effect wrapper
interface GlowProps {
  children: React.ReactNode
  className?: string
  color?: "brand" | "success" | "error"
}

const glowMap = {
  brand: "shadow-[0_0_20px_rgba(59,130,246,0.3)]",
  success: "shadow-[0_0_20px_rgba(34,197,94,0.3)]",
  error: "shadow-[0_0_20px_rgba(239,68,68,0.3)]",
}

export function Glow({ children, className, color = "brand" }: GlowProps) {
  return (
    <div className={cn("transition-shadow duration-300", glowMap[color], className)}>
      {children}
    </div>
  )
}

// Ripple effect on click
interface RippleProps {
  children: React.ReactNode
  className?: string
}

export function Ripple({ children, className }: RippleProps) {
  return (
    <div className={cn("relative overflow-hidden", className)}>
      {children}
      <span className="absolute inset-0 pointer-events-none">
        <span className="absolute inset-0 bg-white/20 scale-0 opacity-0 transition-all duration-500 group-active:scale-150 group-active:opacity-100 group-active:duration-0" />
      </span>
    </div>
  )
}

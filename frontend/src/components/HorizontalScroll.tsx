import type { ReactNode } from "react";

interface HorizontalScrollProps {
  children: ReactNode;
}

export function HorizontalScroll({ children }: HorizontalScrollProps) {
  return (
    <div className="horizontal-scroll">
      {children}
    </div>
  );
}

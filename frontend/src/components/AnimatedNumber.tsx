import { useEffect, useRef } from 'react';
import { animate, useMotionValue, useReducedMotion } from 'framer-motion';

/**
 * A number that smoothly counts up/down to its target — the small bit of motion
 * that makes a metric feel live instead of stamped. Respects prefers-reduced-motion.
 */
export function AnimatedNumber({
  value,
  className,
  duration = 0.9,
}: {
  value: number;
  className?: string;
  duration?: number;
}) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  const mv = useMotionValue(0);

  useEffect(() => {
    if (ref.current == null) return;
    if (reduce) {
      ref.current.textContent = String(Math.round(value));
      return;
    }
    const controls = animate(mv, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        if (ref.current) ref.current.textContent = String(Math.round(v));
      },
    });
    return () => controls.stop();
  }, [value, reduce, duration, mv]);

  return <span ref={ref} className={className}>0</span>;
}

export default AnimatedNumber;

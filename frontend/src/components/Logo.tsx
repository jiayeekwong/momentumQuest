import Image from 'next/image';
import { cn } from '@/src/lib/utils';

interface LogoProps {
  size?: 'sm' | 'md' | 'lg';
  theme?: 'light' | 'dark';
  layout?: 'horizontal' | 'vertical';
  className?: string;
}

const heights = { sm: 40, md: 56, lg: 260 };
const textSizes = { sm: 'text-sm', md: 'text-base', lg: 'text-3xl' };

export function Logo({ size = 'md', theme = 'light', layout, className }: LogoProps) {
  const h = heights[size];
  const showName = layout === 'vertical' || layout === 'horizontal';
  const isVertical = layout === 'vertical';

  return (
    <div className={cn(
      'flex items-center',
      isVertical ? 'flex-col gap-2' : 'gap-1.5',
      className
    )}>
      <Image
        src="/momentumquest-logo.png"
        alt="MomentumQuest"
        width={h}
        height={h}
        style={{ height: h, width: 'auto' }}
        className="object-contain"
        priority
      />
      {showName && (
        <span className={cn(
          'font-black tracking-tight leading-none',
          textSizes[size],
          theme === 'dark' ? 'text-white' : 'text-neutral-900'
        )}>
          MomentumQuest
        </span>
      )}
    </div>
  );
}

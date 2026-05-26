import Image from 'next/image';
import { cn } from '@/src/lib/utils';

interface LogoProps {
  size?: 'sm' | 'md' | 'lg';
  theme?: 'light' | 'dark';
  layout?: 'horizontal' | 'vertical';
  className?: string;
}

const sizeClasses = { sm: 'h-10 w-auto', md: 'h-14 w-auto', lg: 'h-[260px] w-auto' };
const textSizes   = { sm: 'text-sm',    md: 'text-base',  lg: 'text-3xl' };

export function Logo({ size = 'md', theme = 'light', layout, className }: LogoProps) {
  const showName  = layout === 'vertical' || layout === 'horizontal';
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
        width={260}
        height={260}
        className={cn('object-contain', sizeClasses[size])}
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

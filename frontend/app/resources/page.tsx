'use client';

import { useState, useEffect } from 'react';
import { Search, BookOpen, ExternalLink } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';

interface LearningResource {
  id: number;
  skill: string;
  title: string;
  platform: string;
  url: string;
  type: string;
  scraped_at: string;
}

const PLATFORM_COLORS: Record<string, string> = {
  'freeCodeCamp':    'bg-green-700',
  'Microsoft Learn': 'bg-sky-700',
  'Cisco NetAcad':   'bg-blue-800',
  'Codecademy':      'bg-teal-700',
  'Coursera':        'bg-violet-700',
};

export default function ResourcesPage() {
  const [resources, setResources] = useState<LearningResource[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [platform, setPlatform] = useState('All');
  const [search, setSearch] = useState('');

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/resources/`)
      .then((r) => r.json())
      .then((data: LearningResource[]) => setResources(data))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const platforms = ['All', ...Array.from(new Set(resources.map((r) => r.platform))).sort()];

  const filtered = resources.filter((r) => {
    const matchPlatform = platform === 'All' || r.platform === platform;
    const q = search.toLowerCase();
    const matchSearch = !q || r.title.toLowerCase().includes(q) || r.skill.toLowerCase().includes(q);
    return matchPlatform && matchSearch;
  });

  return (
    <DashboardLayout title="Learning Resources">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Curated Learning Paths</h2>
            <p className="text-neutral-500 mt-1">
              Upskill with the best courses handpicked for your career goals.
            </p>
          </div>
          <div className="relative w-full md:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
            <input
              type="text"
              placeholder="Search by title or skill..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
        </div>

        {/* Platform filter tabs — built from live data */}
        <div className="flex flex-wrap gap-2">
          {platforms.map((p) => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={cn(
                'px-4 py-2 rounded-full text-xs font-bold transition-all border',
                platform === p
                  ? 'bg-primary text-white border-primary'
                  : 'bg-white text-neutral-600 border-neutral-200 hover:border-primary/40'
              )}
            >
              {p}
            </button>
          ))}
        </div>

        {/* Loading skeleton */}
        {isLoading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Card key={i} className="p-0 overflow-hidden">
                <div className="h-32 bg-neutral-100 animate-pulse" />
                <div className="p-5 space-y-3">
                  <div className="h-3 bg-neutral-100 rounded animate-pulse w-1/3" />
                  <div className="h-4 bg-neutral-100 rounded animate-pulse w-3/4" />
                  <div className="h-3 bg-neutral-100 rounded animate-pulse w-1/2" />
                </div>
              </Card>
            ))}
          </div>
        )}

        {/* Resource grid */}
        {!isLoading && filtered.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filtered.map((res) => {
              const color = PLATFORM_COLORS[res.platform] ?? 'bg-neutral-700';
              return (
                <Card key={res.id} className="p-0 overflow-hidden flex flex-col group hover:shadow-lg transition-all duration-300">
                  <div className={cn('h-32 flex items-center justify-center p-6 text-white', color)}>
                    <div className="text-center">
                      <BookOpen size={28} className="mx-auto mb-2 opacity-60" />
                      <h5 className="text-base font-black leading-tight line-clamp-2">{res.title}</h5>
                    </div>
                  </div>
                  <div className="p-5 flex-1 flex flex-col gap-3">
                    <div>
                      <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">
                        {res.platform}
                      </p>
                      <h4 className="font-bold text-neutral-900 mt-0.5 line-clamp-2">{res.title}</h4>
                    </div>

                    <Badge variant="neutral" className="text-[9px] px-2 py-0.5 self-start">
                      {res.skill}
                    </Badge>

                    <div className="flex gap-2 mt-auto items-center">
                      <Badge variant="primary" className="text-[9px] shrink-0">{res.type}</Badge>
                      <a href={res.url} target="_blank" rel="noopener noreferrer" className="flex-1">
                        <Button fullWidth size="sm" className="h-8 text-xs">
                          Enrol Now <ExternalLink size={12} className="ml-1" />
                        </Button>
                      </a>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && filtered.length === 0 && (
          <div className="py-20 text-center">
            <BookOpen size={48} className="mx-auto text-neutral-200 mb-4" />
            <h3 className="text-lg font-bold text-neutral-900">No resources found</h3>
            <p className="text-neutral-500 mt-1 text-sm">
              {resources.length === 0
                ? 'No resources have been scraped yet. Run the scraper first.'
                : 'Try adjusting your search or platform filter.'}
            </p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}

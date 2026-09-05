'use client';

/**
 * The privacy notice and the department lists, fetched from the backend.
 *
 * Both used to be hardcoded in the pages that displayed them -- the consent
 * wording in the sign-up form and in two upload panels, the departments in the
 * sign-up form and the admin course form (which had already drifted apart).
 *
 * For the consent wording that duplication was not merely untidy. The notice
 * version written into `user_consents` comes from the server at submit time,
 * so a page showing its own stale copy would record someone as having agreed
 * to text they never saw. The text and the version have to come from the same
 * place, and that place is the server.
 */

import { useEffect, useState } from 'react';
import { API_BASE } from '@/src/lib/apiFetch';

export interface NoticeBlock {
  type: 'paragraph' | 'list';
  text?: string;
  items?: string[];
}

export interface NoticeSection {
  heading: string;
  blocks: NoticeBlock[];
}

export interface DocumentNotice {
  heading: string;
  body: string;
  acknowledgement: string;
}

export interface PrivacyNotice {
  version: string;
  effective_date: string;
  contact_email: string;
  summary: string;
  sections: NoticeSection[];
  consent_statements: Record<string, string>;
  upload_notice: DocumentNotice;
  transcript_notice: DocumentNotice;
  // Null on notice versions that predate CV processing — 1.0 never described
  // it, so it must not appear to have.
  cv_notice: DocumentNotice | null;
  application_disclosure: string;
}

/**
 * Plain fetch, not apiFetch: the sign-up form and the public notice page both
 * need this before a token exists, and apiFetch would bounce a 401 to /login.
 */
export async function fetchPrivacyNotice(): Promise<PrivacyNotice> {
  const res = await fetch(`${API_BASE}/api/auth/privacy-notice/current/`);
  if (!res.ok) throw new Error('privacy notice unavailable');
  return res.json();
}

export function usePrivacyNotice() {
  const [notice, setNotice] = useState<PrivacyNotice | null>(null);
  const [error, setError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchPrivacyNotice()
      .then(data => { if (!cancelled) setNotice(data); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { notice, isLoading, error };
}

export interface Departments {
  departments: string[];
  course_departments: string[];
}

export function useDepartments() {
  const [data, setData] = useState<Departments>({ departments: [], course_departments: [] });

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/auth/departments/`)
      .then(res => (res.ok ? res.json() : Promise.reject(new Error('unavailable'))))
      .then((payload: Departments) => { if (!cancelled) setData(payload); })
      .catch(() => { /* the select simply stays empty; the server validates anyway */ });
    return () => { cancelled = true; };
  }, []);

  return data;
}

/** Splits a notice body on blank lines so it renders as paragraphs. */
export function toParagraphs(body: string): string[] {
  return body.split('\n\n').map(part => part.trim()).filter(Boolean);
}

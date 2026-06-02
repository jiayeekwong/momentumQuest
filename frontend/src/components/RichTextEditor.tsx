'use client';

import { useState, useEffect } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import UnderlineExt from '@tiptap/extension-underline';
import { Bold, Italic, Underline, List } from 'lucide-react';
import { cn } from '@/src/lib/utils';

interface RichTextEditorProps {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
  minHeight?: number;
}

/**
 * Rich-text editor with Bold / Italic / Underline / Bullet-list controls.
 * Stores content as HTML. Mirrors the editor used on the admin announcement form.
 * Controlled: emits HTML via onChange; external value changes are synced in.
 */
export function RichTextEditor({ value, onChange, minHeight = 140 }: RichTextEditorProps) {
  const [, forceUpdate] = useState(0);

  const editor = useEditor({
    immediatelyRender: true,
    extensions: [
      StarterKit.configure({ underline: false }),
      UnderlineExt,
    ],
    content: value || '',
    editorProps: {
      attributes: {
        class: 'tiptap-editor focus:outline-none px-4 py-3 text-sm text-neutral-700 leading-relaxed',
        style: `min-height:${minHeight}px`,
      },
    },
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
      forceUpdate(n => n + 1);
    },
    onSelectionUpdate: () => forceUpdate(n => n + 1),
  });

  // Sync external value (e.g. when an edit form loads existing content).
  // Guard prevents cursor jumps while the user is typing.
  useEffect(() => {
    if (editor && value !== editor.getHTML()) {
      editor.commands.setContent(value || '', { emitUpdate: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, editor]);

  const items = [
    { icon: Bold,      label: 'Bold',      action: () => editor?.chain().focus().toggleBold().run(),       isActive: () => editor?.isActive('bold')       ?? false },
    { icon: Italic,    label: 'Italic',    action: () => editor?.chain().focus().toggleItalic().run(),     isActive: () => editor?.isActive('italic')     ?? false },
    { icon: Underline, label: 'Underline', action: () => editor?.chain().focus().toggleUnderline().run(),  isActive: () => editor?.isActive('underline')  ?? false },
    { icon: List,      label: 'Bullets',   action: () => editor?.chain().focus().toggleBulletList().run(), isActive: () => editor?.isActive('bulletList') ?? false },
  ];

  return (
    <div>
      <div className="flex items-center gap-1 p-1.5 bg-neutral-50 border border-neutral-200 rounded-t-xl border-b-0">
        {items.map(({ icon: Icon, label, action, isActive }) => (
          <button key={label} type="button" onClick={action} title={label}
            className={cn('w-7 h-7 flex items-center justify-center rounded-lg transition-colors',
              isActive() ? 'bg-primary text-white' : 'text-neutral-500 hover:bg-neutral-200')}>
            <Icon size={14} />
          </button>
        ))}
      </div>
      <div className="border border-neutral-300 rounded-b-xl bg-white focus-within:ring-2 focus-within:ring-primary/20">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}

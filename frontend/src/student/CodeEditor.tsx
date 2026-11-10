import { Editor } from "../shared/monaco";

// The student page's code box: the editor VS Code is built on, running in
// the browser. Uncontrolled on purpose -- the parent remounts it per task
// (key={questionId}), so every onChange is the student typing, which is what
// the activity heartbeat counts (see student/App.tsx).
export interface CodeEditorProps {
  language: string;
  initialValue: string;
  onChange: (value: string) => void;
}

export function CodeEditor({ language, initialValue, onChange }: CodeEditorProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white transition-colors focus-within:border-zinc-900">
      <Editor
        height="460px"
        defaultLanguage={language}
        defaultValue={initialValue}
        onChange={(v) => onChange(v ?? "")}
        loading={<span className="text-sm text-zinc-500">Loading editor...</span>}
        options={{
          minimap: { enabled: false },
          fontSize: 14,
          tabSize: 4,
          insertSpaces: true,
          scrollBeyondLastLine: false,
          automaticLayout: true,
          lineNumbersMinChars: 3,
          renderLineHighlight: "none",
          overviewRulerLanes: 0,
          overviewRulerBorder: false,
          hideCursorInOverviewRuler: true,
          padding: { top: 8, bottom: 8 },
          // No autocomplete: it would suggest code, and this is an exercise.
          quickSuggestions: false,
          suggestOnTriggerCharacters: false,
          wordBasedSuggestions: "off",
          parameterHints: { enabled: false },
          placeholder: language === "python" ? "# Your code here." : "// Your code here.",
          ariaLabel: "Your code",
        }}
      />
    </div>
  );
}

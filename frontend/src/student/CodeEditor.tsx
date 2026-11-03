import { Editor } from "../shared/monaco";

// The student page's code box: the editor VS Code is built on, running in
// the browser. Uncontrolled on purpose -- the parent remounts it per task
// (key={questionId}), so every onChange is the student typing, which is what
// the activity heartbeat counts (see student/App.tsx).
export function CodeEditor({
  language,
  initialValue,
  onChange,
}: {
  language: string;
  initialValue: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="code-editor">
      <Editor
        height="320px"
        defaultLanguage={language}
        defaultValue={initialValue}
        onChange={(v) => onChange(v ?? "")}
        loading="Loading editor..."
        options={{
          minimap: { enabled: false },
          fontSize: 14,
          tabSize: 4,
          insertSpaces: true,
          scrollBeyondLastLine: false,
          automaticLayout: true,
          lineNumbersMinChars: 3,
          renderLineHighlight: "line",
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

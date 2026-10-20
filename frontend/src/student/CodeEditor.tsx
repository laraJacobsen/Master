import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
// Editor features (find, bracket matching, folding, ...) and highlighting for
// the question languages only (the cpp contribution registers "c" too) -- not
// the full `monaco-editor` entry, which would also bundle every language
// service (TypeScript, CSS, JSON, ...) we never use.
import "monaco-editor/esm/vs/editor/edcore.main";
import "monaco-editor/esm/vs/basic-languages/python/python.contribution";
import "monaco-editor/esm/vs/basic-languages/cpp/cpp.contribution";
import "monaco-editor/esm/vs/basic-languages/java/java.contribution";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

// Bundled with the app rather than fetched from a CDN (@monaco-editor/react's
// default): a lecture-hall network shouldn't be able to take the editor down.
self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

// The student page's code box: the editor VS Code is built on, running in
// the browser. Uncontrolled on purpose -- the parent remounts it per task
// (key={questionId}), so every onChange is the student typing, which is what
// the activity heartbeat counts (see student/App.tsx).
export function CodeEditor({
  language,
  onChange,
}: {
  language: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="code-editor">
      <Editor
        height="320px"
        defaultLanguage={language}
        defaultValue=""
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

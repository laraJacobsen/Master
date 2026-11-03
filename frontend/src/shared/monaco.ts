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
// Shared by the student code box and the projector view's example editors.
self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

export { Editor, monaco };

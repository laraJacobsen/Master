import type { HintUnlock } from "../shared/types";
import { UNLOCK_LABEL, describeHintPolicy } from "../shared/hintPolicy";
import { Checkbox, FieldHelp, Input, Label, Select } from "../shared/ui";

// The setup page's hint policy fields (backend/hint_policy.py). Kept as text while
// editing, like the page's other number fields; formPayload() turns them into numbers.
export interface HintPolicyForm {
  freeAttempts: string;
  unlock: HintUnlock;
  intervalSeconds: string;
  duplicateSimilarity: string;
  penalty: boolean;
}

export interface HintPolicyFieldsProps {
  value: HintPolicyForm;
  onChange: (next: HintPolicyForm) => void;
}

function whole(text: string, fallback: number): number {
  const n = parseInt(text, 10);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

export function HintPolicyFields({ value, onChange }: HintPolicyFieldsProps) {
  const set = (patch: Partial<HintPolicyForm>) => onChange({ ...value, ...patch });
  const summary = describeHintPolicy({
    free_attempts: whole(value.freeAttempts, 0),
    unlock: value.unlock,
    interval_seconds: whole(value.intervalSeconds, 0),
    duplicate_similarity: 1,
    penalty: value.penalty,
  });

  return (
    <fieldset className="grid gap-4">
      <legend className="mb-1 text-[13px] font-semibold text-zinc-900">Hints &amp; attempts</legend>
      <div className="grid gap-5 sm:grid-cols-[minmax(0,9rem)_minmax(0,1fr)_minmax(0,9rem)]">
        <div>
          <Label htmlFor="f-free-attempts" hint="no hint">
            Free attempts
          </Label>
          <Input
            type="number"
            id="f-free-attempts"
            mono
            min={0}
            max={20}
            step={1}
            value={value.freeAttempts}
            onChange={(e) => set({ freeAttempts: e.target.value })}
          />
        </div>
        <div>
          <Label htmlFor="f-hint-unlock">Next hint unlocks</Label>
          <Select
            id="f-hint-unlock"
            value={value.unlock}
            onChange={(e) => set({ unlock: e.target.value as HintUnlock })}
          >
            {(Object.keys(UNLOCK_LABEL) as HintUnlock[]).map((mode) => (
              <option key={mode} value={mode}>
                {UNLOCK_LABEL[mode]}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="f-hint-interval">Wait (s)</Label>
          <Input
            type="number"
            id="f-hint-interval"
            mono
            min={0}
            max={3600}
            step={10}
            disabled={value.unlock === "attempt"}
            value={value.intervalSeconds}
            onChange={(e) => set({ intervalSeconds: e.target.value })}
          />
        </div>
      </div>
      <FieldHelp>{summary}</FieldHelp>
      <Checkbox
        label="Show students a penalty count (wrong attempts after the free ones; doesn't change the grade)"
        checked={value.penalty}
        onChange={(e) => set({ penalty: e.target.checked })}
      />
    </fieldset>
  );
}

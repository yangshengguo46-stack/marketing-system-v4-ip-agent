"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useI18n } from "@/core/i18n/hooks";
import {
  describeSchedule,
  pad2,
  parseCron,
  serializeCron,
  utcToZonedLocalInput,
  WEEKDAYS,
  zonedLocalToUtcIso,
  type CronParts,
  type CronPreset,
  type ScheduleLocale,
  type Weekday,
} from "@/core/scheduled-tasks/cron";

export type ScheduleValue = {
  schedule_type: "once" | "cron";
  schedule_spec: { cron?: string; run_at?: string };
  timezone: string;
};

const PRESETS: CronPreset[] = [
  "hourly",
  "daily",
  "weekly",
  "monthly",
];

function detectBrowserTimezone(): string {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (typeof tz === "string" && tz.length > 0) {
      return tz;
    }
  } catch {
    // resolvedOptions unavailable
  }
  return "UTC";
}

export function ScheduledTaskScheduleInput({
  initial,
  onChange,
  scheduleTypeLocked = false,
}: {
  initial: ScheduleValue;
  onChange: (value: ScheduleValue) => void;
  scheduleTypeLocked?: boolean;
}) {
  const { t, locale } = useI18n();
  const schedLocale: ScheduleLocale = locale.startsWith("zh") ? "zh" : "en";
  const labels = t.scheduledTasks;

  const [scheduleType, setScheduleType] = useState<"once" | "cron">(
    initial.schedule_type,
  );
  const [preset, setPreset] = useState<CronPreset>(
    () => parseCron(initial.schedule_spec.cron ?? "0 9 * * *").preset,
  );
  const [parts, setParts] = useState<CronParts>(
    () => parseCron(initial.schedule_spec.cron ?? "0 9 * * *").parts,
  );
  const [runAtLocal, setRunAtLocal] = useState<string>(
    initial.schedule_type === "once" && initial.schedule_spec.run_at
      ? utcToZonedLocalInput(
          initial.schedule_spec.run_at,
          initial.timezone || "UTC",
        )
      : "",
  );
  const [timezone] = useState<string>(
    initial.timezone || detectBrowserTimezone(),
  );

  // Hold the latest onChange in a ref so the effect below does not depend on
  // it. This avoids a re-render loop: if the parent passes an inline
  // onChange (new reference each render), depending on it directly would
  // re-fire the effect every render and call onChange again, looping.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Emit on every change including mount. On mount this syncs the parent with
  // the browser-detected timezone and the canonicalized cron, so the submitted
  // value always matches what the user sees in the preview.
  useEffect(() => {
    if (scheduleType === "once") {
      const runAt = runAtLocal ? zonedLocalToUtcIso(runAtLocal, timezone) : "";
      onChangeRef.current({
        schedule_type: "once",
        schedule_spec: runAt ? { run_at: runAt } : {},
        timezone,
      });
      return;
    }
    const cron =
      preset === "custom" ? (parts.raw ?? "") : serializeCron(preset, parts);
    onChangeRef.current({
      schedule_type: "cron",
      schedule_spec: cron ? { cron } : {},
      timezone,
    });
  }, [scheduleType, preset, parts, runAtLocal, timezone]);

  function updateParts(patch: Partial<CronParts>) {
    setParts((prev) => ({ ...prev, ...patch }));
  }

  function changePreset(next: CronPreset) {
    setParts((prev) => {
      const merged = { ...prev };
      if (next === "weekly" && (merged.weekdays ?? []).length === 0) {
        merged.weekdays = ["mon"];
      }
      if (next === "monthly" && merged.dayOfMonth == null) {
        merged.dayOfMonth = 1;
      }
      if (next === "custom" && !merged.raw) {
        merged.raw = serializeCron("daily", prev);
      }
      return merged;
    });
    setPreset(next);
  }

  function toggleWeekday(w: Weekday) {
    setParts((prev) => {
      const set = new Set(prev.weekdays ?? []);
      if (set.has(w)) {
        if (set.size <= 1) {
          return prev;
        }
        set.delete(w);
      } else {
        set.add(w);
      }
      return { ...prev, weekdays: WEEKDAYS.filter((d) => set.has(d)) };
    });
  }

  const preview = describeSchedule(
    { scheduleType, preset, parts, runAtLocal, timezone },
    schedLocale,
  );
  const visiblePreview = preview.replace(/\s*\([^)]*\)\s*$/, "");

  return (
    <div className="flex flex-col gap-2" data-testid="schedule-input">
      {!scheduleTypeLocked && (
        <div className="flex flex-wrap gap-2">
          <Button
            variant={scheduleType === "cron" ? "default" : "outline"}
            size="sm"
            onClick={() => setScheduleType("cron")}
          >
            {labels.scheduleType.cron}
          </Button>
          <Button
            variant={scheduleType === "once" ? "default" : "outline"}
            size="sm"
            onClick={() => setScheduleType("once")}
          >
            {labels.scheduleType.once}
          </Button>
        </div>
      )}

      {scheduleType === "cron" ? (
        <>
          <Select
            value={preset}
            onValueChange={(v) => changePreset(v as CronPreset)}
          >
            <SelectTrigger className="w-full" data-testid="schedule-preset">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PRESETS.map((p) => (
                <SelectItem key={p} value={p}>
                  {labels.preset[p]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {preset === "hourly" && (
            <Input
              type="number"
              min={0}
              max={59}
              value={parts.minute ?? 0}
              onChange={(e) => updateParts({ minute: Number(e.target.value) })}
              aria-label={labels.fields.minute}
            />
          )}

          {(preset === "daily" ||
            preset === "weekly" ||
            preset === "monthly") && (
            <Input
              type="time"
              value={`${pad2(parts.hour ?? 9)}:${pad2(parts.minute ?? 0)}`}
              onChange={(e) => {
                const [h, m] = e.target.value.split(":").map(Number);
                updateParts({ hour: h, minute: m });
              }}
              aria-label={labels.fields.time}
            />
          )}

          {preset === "weekly" && (
            <div className="flex flex-wrap gap-1">
              <span className="text-muted-foreground w-full text-sm">
                {labels.fields.weekday}
              </span>
              {WEEKDAYS.map((w) => {
                const active = (parts.weekdays ?? []).includes(w);
                return (
                  <Button
                    key={w}
                    variant={active ? "default" : "outline"}
                    size="sm"
                    onClick={() => toggleWeekday(w)}
                    aria-pressed={active}
                  >
                    {labels.weekdays[w]}
                  </Button>
                );
              })}
            </div>
          )}

          {preset === "monthly" && (
            <Input
              type="number"
              min={1}
              max={31}
              value={parts.dayOfMonth ?? 1}
              onChange={(e) =>
                updateParts({ dayOfMonth: Number(e.target.value) })
              }
              aria-label={labels.fields.dayOfMonth}
            />
          )}

          {preset === "custom" && (
            <p className="text-muted-foreground text-sm">
              {labels.preset.custom}
            </p>
          )}
        </>
      ) : (
        <Input
          type="datetime-local"
          value={runAtLocal}
          onChange={(e) => setRunAtLocal(e.target.value)}
          aria-label={labels.fields.runAt}
        />
      )}

      <div
        className="text-muted-foreground text-sm"
        data-testid="schedule-preview"
      >
        {visiblePreview}
      </div>
    </div>
  );
}

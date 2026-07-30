import { parseSlashSkillReference } from "./slash";

const INTERNAL_SKILL_TOOL_RE = /(?:^|_)skill(?:_|$)|skill/i;
const INTERNAL_SKILL_VALUE_RE =
  /(?:^|[/\\])(?:mnt[/\\])?skills[/\\]|SKILL\.md|\.skill(?:$|[\s?#/\\])/i;

function containsInternalSkillValue(value: unknown): boolean {
  if (typeof value === "string") {
    return INTERNAL_SKILL_VALUE_RE.test(value);
  }
  if (Array.isArray(value)) {
    return value.some(containsInternalSkillValue);
  }
  if (value && typeof value === "object") {
    return Object.values(value).some(containsInternalSkillValue);
  }
  return false;
}

/**
 * Skill selection and loading are product internals. They may remain in the
 * persisted run for replay and diagnosis, but must not become customer-facing
 * execution steps.
 */
export function isInternalSkillToolCall(
  name: string,
  args: Record<string, unknown> = {},
): boolean {
  return (
    INTERNAL_SKILL_TOOL_RE.test(name) || containsInternalSkillValue(args)
  );
}

/**
 * Keep the user's actual request visible while removing an explicit internal
 * slash-skill selector from chat, copy and export surfaces.
 */
export function stripSkillSelectorForDisplay(content: string): string {
  const reference = parseSlashSkillReference(content);
  return reference ? reference.remainingText : content;
}

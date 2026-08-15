import type { DeskRegistration } from "../types";
import { Badge, Empty, Panel, deskLabel } from "./ui";

/** The agent registry, in newsroom language. Permissions here *are* the evidence
 * boundaries the router enforces — a desk cannot receive evidence it isn't
 * registered for. The version badge is the agent actually constructed in this
 * process, so it reads `adk-…` on a live fleet and `fixture-…` on the recorded
 * demo without the screen having to be told which one it is. */
export function Masthead({
  desks,
  implementation,
}: {
  desks: DeskRegistration[];
  implementation?: string;
}) {
  return (
    <Panel
      title="Masthead"
      subtitle={`approved desks, versions, and evidence permissions${
        implementation ? ` · ${implementation} agents` : ""
      }`}
    >
      {desks.length === 0 && <Empty>Registry unavailable.</Empty>}
      <ul className="space-y-2">
        {desks.map((desk) => (
          <li key={desk.desk} className="rounded border border-stone-800 bg-stone-950/50 px-2.5 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-medium text-stone-200">{deskLabel(desk.desk)}</span>
              <Badge
                title={
                  desk.registered_version && desk.registered_version !== desk.agent_version
                    ? `registered as ${desk.registered_version}`
                    : undefined
                }
              >
                {desk.agent_version}
              </Badge>
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-stone-500">{desk.responsibility}</p>
            <div className="mt-1.5 flex flex-wrap gap-1">
              {desk.permissions.map((permission) => (
                <Badge key={permission} tone="info">
                  {permission}
                </Badge>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

import { ChevronDown } from "lucide-react";

type NoticeSection = {
  title: string;
  body: string;
};

export default function LegalDisclosure({
  title,
  summary,
  sections,
}: {
  title: string;
  summary: string;
  sections: NoticeSection[];
}) {
  return (
    <details className="rounded-[1.2rem] border border-[#13212c]/8 bg-white/65">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3.5 py-3 text-sm font-medium text-[#13212c] sm:px-4">
        <div>
          <p>{title}</p>
          <p className="mt-1 text-[11px] font-normal uppercase tracking-[0.12em] text-[#7a8894] sm:text-xs sm:tracking-[0.14em]">{summary}</p>
        </div>
        <ChevronDown size={16} className="shrink-0 text-[#61717d]" />
      </summary>
      <div className="border-t border-[#13212c]/8 px-3.5 py-3 sm:px-4 sm:py-4">
        <div className="space-y-3 sm:space-y-4">
          {sections.map((section) => (
            <div key={section.title} className="rounded-[1rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3">
              <p className="text-sm font-semibold text-[#13212c]">{section.title}</p>
              <p className="mt-1.5 text-sm leading-6 text-[#586773]">{section.body}</p>
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}

import * as RadixTabs from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

interface Tab {
  id: string;
  label: string;
}

interface TabsProps {
  tabs: Tab[];
  active: string;
  onChange: (id: string) => void;
}

export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <RadixTabs.Root value={active} onValueChange={onChange} className="border-b border-border">
      <RadixTabs.List className="-mb-px flex gap-6">
        {tabs.map((tab) => (
          <RadixTabs.Trigger
            key={tab.id}
            value={tab.id}
            className={cn(
              "whitespace-nowrap border-b-2 border-transparent pb-3 text-sm font-medium text-muted-foreground transition-colors",
              "hover:border-border hover:text-foreground",
              "data-[state=active]:border-secondary data-[state=active]:text-secondary",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-t",
            )}
          >
            {tab.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
    </RadixTabs.Root>
  );
}

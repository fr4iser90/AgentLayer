/**
 * The navigation model — one place that decides what the rail contains.
 *
 * Before this, five components each carried their own nav container: the top
 * bar in `AppLayout` (five items visible, six behind a `More` dropdown), plus
 * sidebars in `SettingsLayout`, `AdminLayout`, `OrgAdminLayout` and
 * `InterfacesLayout`. The last two nested *inside* another sidebar, so
 * `/admin/interfaces/voice` was three containers deep and `/settings/*` two.
 * Nothing could answer "how deep is this area" or "can a user reach it at all",
 * because the answer was spread over five files.
 *
 * The model here is one rail whose contents are chosen by route. Three rules:
 *
 * - **Two levels, never three.** A surface has sections, a section has leaves.
 *   A leaf that mounts another nav container is a modelling error — entering
 *   `/admin/interfaces` now swaps the rail's sections instead of adding a
 *   second one beside it.
 * - **Everything visible.** There is no `more` bucket. An item that must not
 *   appear for this user is filtered out by `navItemAllowed`, not demoted into
 *   a dropdown.
 * - **Every surface carries its way out.** Non-app surfaces end in a
 *   "back to app" leaf, because the app's own items are not on screen there.
 */

import {
  Activity,
  BookOpen,
  Bot,
  BriefcaseBusiness,
  Brain,
  CalendarClock,
  Clock,
  Cpu,
  ExternalLink,
  FolderKanban,
  Gauge,
  GitBranch,
  Home,
  KeyRound,
  Layers,
  LayoutDashboard,
  Link as LinkIcon,
  MessagesSquare,
  Mic,
  Radio,
  ScrollText,
  Settings as SettingsIcon,
  Share2,
  Shield,
  SlidersHorizontal,
  Sparkles,
  UploadCloud,
  Users,
  Workflow,
  Wrench,
  type LucideIcon
} from "lucide-react";
import type { AuthUser } from "../auth/AuthContext";
import { friendSystemEnabled, navItemAllowed, type NavItemId } from "../auth/tenantSurface";
import { isSingleUser } from "../auth/deploymentMode";
import { canManageWorkspaceGrants } from "../pages/admin/accessGating";

export type NavLeaf = {
  to: string;
  /** i18n key, resolved against the surface's namespace. */
  labelKey: string;
  icon: LucideIcon;
  /** Match the route exactly — without it `/` is active on every path. */
  end?: boolean;
  /** Tenant allowlist id; admin/org/settings leaves are gated by their guards. */
  nav?: NavItemId;
  /** The leaf leaves the app: `to` is a full URL, rendered as `<a>`. */
  external?: boolean;
};

export type NavSection = {
  /** Section heading. Omitted for an ungrouped run of leaves. */
  labelKey?: string;
  leaves: NavLeaf[];
};

export type NavSurface = {
  id: "app" | "settings" | "admin" | "org";
  /** Namespace the labels in this surface resolve against. */
  namespace: string;
  /**
   * Heading above the rail. Only the non-app surfaces have one: their items are
   * a slice of the product, and the reader needs to know which slice. The app
   * rail is the product, and the header already says its name.
   */
  titleKey?: string;
  ariaKey: string;
  sections: NavSection[];
};

const GITHUB_REPO =
  "https://github.com/fr4iser90/AgentLayer_-_Jetson-Orin-Nano-Super-Developer-Kit-dedicated";

const APP_SECTIONS: NavSection[] = [
  {
    leaves: [
      { to: "/", labelKey: "nav.home", icon: Home, end: true, nav: "home" },
      { to: "/chat", labelKey: "nav.chat", icon: MessagesSquare, nav: "chat" }
    ]
  },
  {
    labelKey: "nav.workspace",
    leaves: [
      { to: "/studio", labelKey: "nav.studio", icon: Sparkles, nav: "studio" },
      { to: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard, nav: "dashboard" },
      { to: "/projects", labelKey: "nav.projects", icon: FolderKanban, nav: "projects" },
      { to: "/schedules", labelKey: "nav.schedules", icon: Clock, nav: "schedules" },
      { to: "/tasks", labelKey: "nav.tasks", icon: BriefcaseBusiness, nav: "tasks" }
    ]
  },
  {
    labelKey: "nav.sharing",
    leaves: [
      { to: "/settings/shares", labelKey: "nav.shares", icon: Share2, nav: "shares" },
      { to: "/settings/friends", labelKey: "nav.friends", icon: Users, nav: "friends" }
    ]
  },
  {
    labelKey: "nav.resources",
    leaves: [
      { to: "/docs", labelKey: "nav.docs", icon: BookOpen },
      { to: "/settings/profile", labelKey: "common:settings", icon: SettingsIcon },
      {
        to: GITHUB_REPO,
        external: true,
        labelKey: "nav.github",
        icon: ExternalLink
      }
    ]
  }
];

const SETTINGS_SECTIONS: NavSection[] = [
  {
    labelKey: "settings:navAccount",
    leaves: [
      { to: "/settings/profile", labelKey: "settings:profileTitle", icon: Users },
      { to: "/settings/notifications", labelKey: "settings:notificationsTitle", icon: Activity },
      { to: "/settings/connections", labelKey: "settings:connectionsTitle", icon: LinkIcon }
    ]
  },
  {
    labelKey: "settings:navAgent",
    leaves: [
      { to: "/settings/tools", labelKey: "settings:toolsTitle", icon: Wrench },
      { to: "/settings/agent", labelKey: "settings:agentTitle", icon: Bot },
      { to: "/settings/delegate", labelKey: "settings:delegateNav", icon: Layers },
      { to: "/settings/voice", labelKey: "settings:voiceTitle", icon: Mic }
    ]
  },
  {
    labelKey: "settings:navSharing",
    leaves: [
      { to: "/settings/shares", labelKey: "settings:sharesTitle", icon: Share2, nav: "shares" },
      { to: "/settings/friends", labelKey: "settings:friendsTitle", icon: Users, nav: "friends" }
    ]
  }
];

const ADMIN_SECTIONS: NavSection[] = [
  { leaves: [{ to: "/admin", labelKey: "admin:overview", icon: Gauge, end: true }] },
  {
    labelKey: "admin:navPlatform",
    leaves: [
      { to: "/admin/interfaces", labelKey: "admin:interfacesTitle", icon: Radio },
      { to: "/admin/tools", labelKey: "admin:toolsRegistryTitle", icon: Wrench },
      { to: "/admin/agents", labelKey: "admin:agentsTitle", icon: Bot },
      {
        to: "/admin/agent-submissions",
        labelKey: "admin:agentSubmissionsNavTitle",
        icon: UploadCloud
      }
    ]
  },
  {
    labelKey: "admin:navAutomation",
    leaves: [
      { to: "/admin/schedules", labelKey: "admin:schedulesTitle", icon: CalendarClock },
      { to: "/admin/scheduled-jobs", labelKey: "admin:pluginCron", icon: Workflow }
    ]
  },
  {
    labelKey: "admin:navObservability",
    leaves: [
      { to: "/admin/benchmarks", labelKey: "admin:benchNav", icon: Activity },
      { to: "/admin/agent-config", labelKey: "admin:agentConfigNav", icon: SlidersHorizontal },
      { to: "/admin/run-traces", labelKey: "admin:runTraces", icon: ScrollText }
    ]
  }
];

/**
 * The interfaces area's nine pages.
 *
 * These were a second sidebar mounted *inside* the admin one, which is what put
 * `/admin/interfaces/*` three containers deep. They are ordinary leaves now,
 * spliced into the admin rail while the user is inside the area: moving between
 * two interface settings is one click, and so is leaving for `/admin/tools`.
 */
const INTERFACES_SECTIONS: NavSection[] = [
  {
    labelKey: "admin:interfacesTitle",
    leaves: [
      { to: "/admin/interfaces", labelKey: "admin:overview", icon: Gauge, end: true },
      { to: "/admin/interfaces/bridges", labelKey: "admin:bridges", icon: GitBranch },
      { to: "/admin/interfaces/providers", labelKey: "admin:interfacesProvidersTitle", icon: Cpu },
      {
        to: "/admin/interfaces/model-policies",
        labelKey: "admin:interfacesModelPoliciesTitle",
        icon: KeyRound
      },
      { to: "/admin/interfaces/routing", labelKey: "admin:interfacesRoutingTitle", icon: Layers },
      { to: "/admin/interfaces/memory", labelKey: "admin:memoryRagTitle", icon: Brain },
      { to: "/admin/interfaces/voice", labelKey: "admin:interfacesVoiceTitle", icon: Mic },
      {
        to: "/admin/interfaces/automation",
        labelKey: "admin:interfacesAutomationTitle",
        icon: Workflow
      },
      { to: "/admin/interfaces/platform", labelKey: "admin:interfacesPlatformTitle", icon: Shield }
    ]
  }
];

const BACK_TO_APP: NavLeaf = { to: "/", labelKey: "nav.backToApp", icon: Home, end: true };

function withBackToApp(sections: NavSection[]): NavSection[] {
  return [...sections, { leaves: [BACK_TO_APP] }];
}

function filterSections(sections: NavSection[], user: AuthUser | null | undefined): NavSection[] {
  return sections
    .map((section) => ({
      ...section,
      leaves: section.leaves.filter((leaf) => !leaf.nav || navItemAllowed(user, leaf.nav))
    }))
    .filter((section) => section.leaves.length > 0);
}

export function appNav(user: AuthUser | null | undefined): NavSurface {
  return {
    id: "app",
    namespace: "common",
    ariaKey: "nav.sectionsAria",
    sections: filterSections(APP_SECTIONS, user)
  };
}

export function settingsNav(user: AuthUser | null | undefined): NavSurface {
  const sections = SETTINGS_SECTIONS.map((section) =>
    section.labelKey === "settings:navSharing" && !friendSystemEnabled(user)
      ? { ...section, leaves: [] }
      : section
  );
  return {
    id: "settings",
    namespace: "settings",
    titleKey: "common:settings",
    ariaKey: "settings:settingsSectionsAria",
    sections: withBackToApp(filterSections(sections, user))
  };
}

export function adminNav(user: AuthUser | null | undefined, pathname: string): NavSurface {
  const sections = [...ADMIN_SECTIONS];
  if (!isSingleUser(user)) {
    sections.push({
      labelKey: "admin:navPeople",
      leaves: [{ to: "/admin/users", labelKey: "admin:usersTitle", icon: Users }]
    });
  }
  if (isInterfacesArea(pathname)) {
    sections.push(...INTERFACES_SECTIONS);
  }
  return {
    id: "admin",
    namespace: "admin",
    titleKey: "admin:operatorAdmin",
    ariaKey: "admin:adminSectionsAria",
    sections: withBackToApp(sections)
  };
}

export function orgNav(user: AuthUser | null | undefined): NavSurface {
  const leaves = [
    { to: "/org/knowledge", labelKey: "org:navKnowledge", icon: BookOpen },
    { to: "/org/team", labelKey: "org:navTeam", icon: Users }
  ];
  if (canManageWorkspaceGrants(user)) {
    leaves.push({ to: "/org/grants", labelKey: "org:navGrants", icon: Share2 });
  }
  return {
    id: "org",
    namespace: "org",
    titleKey: "org:sidebarTitle",
    ariaKey: "org:sidebarAria",
    // One run of leaves: the old rail wrapped each item in a group whose heading
    // repeated the item's own label.
    sections: withBackToApp([{ leaves }])
  };
}

/** True while inside the interfaces area, where its section joins the rail. */
export function isInterfacesArea(pathname: string): boolean {
  return pathname.startsWith("/admin/interfaces");
}

/**
 * The rail for a path.
 *
 * `AppLayout` calls this once per render, which is what keeps exactly one nav
 * container on screen: the surfaces replace each other rather than nesting.
 */
export function surfaceForPath(
  pathname: string,
  user: AuthUser | null | undefined
): NavSurface {
  if (pathname.startsWith("/admin")) return adminNav(user, pathname);
  if (pathname.startsWith("/org")) return orgNav(user);
  if (pathname.startsWith("/settings")) return settingsNav(user);
  return appNav(user);
}

/** Every leaf of a surface, flattened — what the reachability guard reads. */
export function navLeaves(surface: NavSurface): NavLeaf[] {
  return surface.sections.flatMap((section) => section.leaves);
}
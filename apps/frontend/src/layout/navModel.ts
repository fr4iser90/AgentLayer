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
 * - **One `nav`, never a second one.** A surface has sections, a section has
 *   leaves, and a leaf may fold the pages below it inside the same list
 *   (`children`). What is forbidden is a leaf that mounts another nav container:
 *   that is how `/admin/interfaces/voice` became three containers deep.
 *   `check-nav-depth.mjs` counts the containers on screen and the depth of a
 *   `children` list, so neither grows by accident.
 * - **Everything visible.** There is no `more` bucket. An item that must not
 *   appear for this user is filtered out by `navItemAllowed`, not demoted into
 *   a dropdown. A fold belongs to the reader, not to the model — it defaults to
 *   open while the route is inside it, and the guard reads this file rather than
 *   the rendered list, so collapsing can never make an area unreachable.
 * - **Every surface carries its way out.** Non-app surfaces end in a
 *   "back to app" leaf, because the app's own items are not on screen there.
 */

import {
  Activity,
  BookOpen,
  Bot,
  BriefcaseBusiness,
  Brain,
  Building2,
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
  ShieldCheck,
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
import { hasOrgSurface, isSingleUser } from "../auth/deploymentMode";
import {
  canManageWorkspaceGrants,
  canReachOrgSurface,
  isSiteAdmin
} from "../pages/admin/accessGating";

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
  /**
   * Pages below this leaf, folded under it inside the same list.
   *
   * The leaf stays a link, so folding never costs the area its own page: the
   * row for `/admin/interfaces` goes there and its chevron opens the eight
   * settings below it. One level only — a child with children is the nested
   * sidebar this model deleted, and `check-nav-depth.mjs` fails it.
   */
  children?: NavLeaf[];
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

/**
 * The eight settings pages below `/admin/interfaces`.
 *
 * These were a second sidebar mounted *inside* the admin one, which is what put
 * `/admin/interfaces/*` three containers deep. They are leaves of the admin rail
 * now, folded under the door that opens the area rather than standing beside it:
 * the area used to be in the same list twice — `Interfaces` in the platform
 * section and `Overview` in a section of its own, two rows for one page, both
 * lit at once because a `NavLink` without `end` matches its descendants.
 *
 * They are no longer spliced in by path either. The rail had one shape outside
 * the area and another inside it, so every hop between two interface settings
 * rebuilt the list under the pointer; now the list is fixed and only its fold
 * changes, which is also what lets the fold be a preference rather than a
 * surprise.
 */
const INTERFACES_CHILDREN: NavLeaf[] = [
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
  { to: "/admin/interfaces/automation", labelKey: "admin:interfacesAutomationTitle", icon: Workflow },
  { to: "/admin/interfaces/platform", labelKey: "admin:interfacesPlatformTitle", icon: Shield }
];

const ADMIN_SECTIONS: NavSection[] = [
  { leaves: [{ to: "/admin", labelKey: "admin:overview", icon: Gauge, end: true }] },
  {
    labelKey: "admin:navPlatform",
    leaves: [
      {
        to: "/admin/interfaces",
        labelKey: "admin:interfacesTitle",
        icon: Radio,
        children: INTERFACES_CHILDREN
      },
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

/** A door into another surface, plus the runtime question that opens it. */
interface SurfaceDoor extends NavLeaf {
  open: (user: AuthUser | null | undefined) => boolean;
}

/**
 * The doors into the other surfaces.
 *
 * These lived in the avatar menu, which is the one place the "everything
 * visible" rule can quietly die: an operator sitting in `/chat` had to open a
 * face to find the admin area, and `AppShell` renders that menu on every surface,
 * so the same link also sat beside a rail that already carried the page.
 *
 * The menu also had its own, narrower copy of the gate — `membership_role` was
 * tenant_owner or tenant_admin, nothing else — while `RequireOrgAdmin` admits a
 * content editor and a delegated grants holder too. Those two reach
 * `/org/knowledge` fine and had no link to it anywhere, because the org area's
 * leaves only join the rail once you are already inside the area. Both doors now
 * ask the predicate the route guard asks.
 *
 * Neither carries a `nav` id: the tenant allowlist in `allowed_nav` lists
 * consumer items, and hiding the operator's own door behind a consumer setting
 * is how an admin locks themselves out of the screen that would unlock it.
 *
 * A `const` list with the gate beside each door, not pushes inside a function:
 * `check-nav-depth.mjs` reads the app rail's doors out of this source, and a
 * roleless guard run would see an empty section built at runtime and call every
 * surface door missing.
 */
const SURFACE_DOORS: SurfaceDoor[] = [
  { to: "/admin", labelKey: "nav.admin", icon: ShieldCheck, open: (u) => isSiteAdmin(u) },
  {
    to: "/org",
    labelKey: "nav.org",
    icon: Building2,
    // `hasOrgSurface` stays beside the door rather than inside
    // `canReachOrgSurface`, so the deployment mode remains visible in the model.
    open: (u) => hasOrgSurface(u) && canReachOrgSurface(u)
  }
];

function managementSection(user: AuthUser | null | undefined): NavSection | null {
  const leaves = SURFACE_DOORS.filter((door) => door.open(user)).map(
    ({ to, labelKey, icon }) => ({ to, labelKey, icon })
  );
  return leaves.length ? { labelKey: "nav.management", leaves } : null;
}

export function appNav(user: AuthUser | null | undefined): NavSurface {
  const doors = managementSection(user);
  return {
    id: "app",
    namespace: "common",
    ariaKey: "nav.sectionsAria",
    sections: filterSections(doors ? [...APP_SECTIONS, doors] : APP_SECTIONS, user)
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

export function adminNav(user: AuthUser | null | undefined): NavSurface {
  const sections = [...ADMIN_SECTIONS];
  if (!isSingleUser(user)) {
    sections.push({
      labelKey: "admin:navPeople",
      leaves: [{ to: "/admin/users", labelKey: "admin:usersTitle", icon: Users }]
    });
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

/**
 * The rail for a path.
 *
 * `AppLayout` calls this once per render, which is what keeps exactly one nav
 * container on screen: the surfaces replace each other rather than nesting.
 * Inside `/admin/interfaces` the rail does not change at all — the area's pages
 * hang under their door in the admin rail, folded open — so moving between two
 * of them leaves the list where it was.
 */
export function surfaceForPath(
  pathname: string,
  user: AuthUser | null | undefined
): NavSurface {
  if (pathname.startsWith("/admin")) return adminNav(user);
  if (pathname.startsWith("/org")) return orgNav(user);
  if (pathname.startsWith("/settings")) return settingsNav(user);
  return appNav(user);
}

/**
 * Every leaf of a surface, flattened — what the reachability guard reads.
 *
 * Children come with their door, because "is this page in the rail" has the
 * same answer whether or not the reader has it folded shut at the moment.
 */
export function navLeaves(surface: NavSurface): NavLeaf[] {
  return surface.sections.flatMap((section) =>
    section.leaves.flatMap((leaf) => [leaf, ...navLeavesOf(leaf)])
  );
}

function navLeavesOf(leaf: NavLeaf): NavLeaf[] {
  return (leaf.children ?? []).flatMap((child) => [child, ...navLeavesOf(child)]);
}
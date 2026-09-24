/**
 * Per-site width migration table.
 *
 * A value-level map cannot work here. `max-w-md` appears 41 times and is a form
 * control in 28 of them and a modal in 7 — same value, different purpose, and
 * the whole point of the ramp is that purpose is the name. So the ambiguous
 * values are mapped by site, from the classification pass over all 183 call
 * sites.
 *
 * Entries are { line, from, to }. Applied bottom-up per file so earlier line
 * numbers stay valid while later ones are rewritten.
 *
 * `to: null` deletes the class outright — used where the idiom itself is being
 * retired rather than renamed.
 */

/** @type {Record<string, Array<{line: number, from: string, to: string|null}>>} */
export const MIGRATION = {
  // ---------------------------------------------------------------- controls
  // xs (320) is uniformly numbers and short enums; md (448) uniformly text,
  // IDs and model keys. Those two are the one size split in the old set that
  // was a real decision rather than drift, so both survive as their own token.
  "src/pages/TasksPage.tsx": [
    { line: 260, from: "md", to: "controlWide" },
    { line: 175, from: "4xl", to: "page" },
  ],
  "src/pages/admin/AdminBenchmarks.tsx": [
    { line: 1890, from: "md", to: "controlWide" },
    { line: 2526, from: "md", to: "controlWide" },
    { line: 396, from: "[10rem]", to: "chip" },
    { line: 399, from: "[12rem]", to: "chipWide" },
    { line: 402, from: "[16rem]", to: "chipWide" },
    { line: 723, from: "[10rem]", to: "chip" },
    { line: 726, from: "[10rem]", to: "chip" },
    { line: 729, from: "[10rem]", to: "chip" },
    { line: 733, from: "[10rem]", to: "chip" },
    { line: 3047, from: "full", to: "chipWide" },
    { line: 3309, from: "md", to: "dialog" },
  ],
  "src/pages/admin/interfaces/AdminInterfacesAutomationSection.tsx": [
    { line: 57, from: "md", to: "controlWide" },
    { line: 41, from: "xl", to: "controlWide" },
    { line: 32, from: "xs", to: "control" },
    { line: 70, from: "xs", to: "control" },
    { line: 92, from: "xs", to: "control" },
    { line: 111, from: "xs", to: "control" },
    { line: 124, from: "xs", to: "control" },
  ],
  "src/pages/admin/interfaces/AdminInterfacesBridgesSection.tsx": [
    { line: 108, from: "md", to: "controlWide" },
    { line: 116, from: "md", to: "controlWide" },
    { line: 191, from: "md", to: "controlWide" },
    { line: 199, from: "md", to: "controlWide" },
    { line: 229, from: "xs", to: "control" },
  ],
  "src/pages/admin/interfaces/AdminInterfacesLegalSection.tsx": [
    { line: 35, from: "md", to: "controlWide" },
    { line: 98, from: "md", to: "controlWide" },
  ],
  "src/pages/admin/interfaces/AdminInterfacesLlmSection.tsx": [
    { line: 1337, from: "md", to: "controlWide" },
    { line: 994, from: "xs", to: "control" },
    { line: 1485, from: "xs", to: "control" },
    { line: 1499, from: "xs", to: "control" },
    { line: 1514, from: "xs", to: "control" },
    { line: 1362, from: "xl", to: "measure" },
    { line: 1278, from: "[48%]", to: null },
  ],
  "src/pages/admin/interfaces/AdminInterfacesMemorySection.tsx": [
    { line: 174, from: "md", to: "controlWide" },
    { line: 258, from: "md", to: "controlWide" },
    { line: 364, from: "md", to: "controlWide" },
    { line: 514, from: "xl", to: "measure" },
    { line: 623, from: "xl", to: "measure" },
  ],
  "src/pages/admin/interfaces/AdminInterfacesPlatformSection.tsx": [
    { line: 113, from: "md", to: "controlWide" },
    { line: 456, from: "md", to: "controlWide" },
    { line: 546, from: "md", to: "controlWide" },
    { line: 602, from: "md", to: "controlWide" },
    { line: 631, from: "md", to: "controlWide" },
    { line: 662, from: "md", to: "controlWide" },
    { line: 141, from: "xs", to: "control" },
    { line: 205, from: "xs", to: "control" },
    { line: 218, from: "xs", to: "control" },
    { line: 256, from: "xs", to: "control" },
    { line: 268, from: "xs", to: "control" },
    { line: 280, from: "xs", to: "control" },
    { line: 493, from: "xs", to: "control" },
  ],
  "src/pages/settings/ConnectionsSettings.tsx": [
    { line: 322, from: "md", to: "controlWide" },
    { line: 381, from: "md", to: "controlWide" },
    { line: 306, from: "2xl", to: "page" },
  ],
  "src/pages/settings/DelegateSettings.tsx": [
    { line: 289, from: "md", to: "controlWide" },
    { line: 555, from: "md", to: "controlWide" },
    { line: 145, from: "xs", to: "control" },
    { line: 269, from: "xs", to: "control" },
    // A wide textarea is a writing column, not a one-line control.
    { line: 366, from: "2xl", to: "measure" },
    { line: 528, from: "2xl", to: "measure" },
    { line: 504, from: "3xl", to: "pageNarrow" },
  ],
  "src/pages/settings/ToolsSettings.tsx": [
    { line: 342, from: "md", to: "controlWide" },
    { line: 301, from: "4xl", to: "page" },
    { line: 589, from: "lg", to: "drawer" },
  ],
  "src/pages/settings/VoiceSettings.tsx": [
    { line: 107, from: "md", to: "controlWide" },
    { line: 140, from: "md", to: "controlWide" },
    { line: 152, from: "md", to: "controlWide" },
    { line: 120, from: "xs", to: "control" },
    { line: 129, from: "xs", to: "control" },
    { line: 67, from: "2xl", to: "page" },
  ],
  "src/features/admin/benchmarks/BenchmarkStatsPanel.tsx": [
    { line: 346, from: "[11rem]", to: "control" },
  ],
  "src/features/dashboard/CardGridBlock.tsx": [
    { line: 134, from: "xs", to: "control" },
  ],
  "src/features/chat/ContextInjectionBadge.tsx": [
    { line: 35, from: "[16rem]", to: "chipWide" },
  ],
  "src/pages/admin/AdminUsers.tsx": [
    { line: 668, from: "[14rem]", to: "control" },
    { line: 587, from: "4xl", to: "page" },
    // Skeleton bars: the width is a placeholder, not a design value.
    { line: 77, from: "[9rem]", to: "chip" },
    { line: 81, from: "[5rem]", to: "chip" },
  ],

  // ------------------------------------------------------------------ modals
  "src/components/ConfirmModal.tsx": [{ line: 58, from: "md", to: "dialog" }],
  "src/pages/DashboardPublicSharePage.tsx": [
    { line: 141, from: "md", to: "dialog" },
    { line: 124, from: "lg", to: "dialog" },
    { line: 169, from: "lg", to: "dialog" },
  ],
  "src/features/dashboard/ProjectsImportModal.tsx": [
    { line: 235, from: "2xl", to: "dialogWide" },
  ],
  "src/features/workspace/WorkspaceMcpModal.tsx": [
    { line: 181, from: "2xl", to: "dialogWide" },
  ],
  "src/pages/MySchedulesPage.tsx": [
    { line: 478, from: "2xl", to: "dialogWide" },
    { line: 645, from: "2xl", to: "dialogWide" },
    { line: 712, from: "4xl", to: "dialogFull" },
    { line: 356, from: "5xl", to: "pageWide" },
  ],
  "src/pages/admin/AdminSchedules.tsx": [
    { line: 513, from: "2xl", to: "dialogWide" },
    { line: 677, from: "2xl", to: "dialogWide" },
    { line: 316, from: "5xl", to: "pageWide" },
  ],
  "src/features/dashboard/DashboardLayoutProposalPanel.tsx": [
    // Carries a grid preview, so it keeps the full modal width.
    { line: 81, from: "5xl", to: "dialogFull" },
    { line: 121, from: "[14rem]", to: "chipWide" },
  ],

  // ----------------------------------------------------------------- drawers
  "src/features/dashboard/BlockSettingsModal.tsx": [
    // Base `max-w-md` with `sm:max-w-lg` on the same element: below 640px the
    // base applies, above it the sm: variant does. Both become one drawer width
    // so the two breakpoints stop disagreeing.
    { line: 265, from: "md", to: "drawer" },
    { line: 265, from: "lg", to: "drawer" },
  ],
  "src/features/dashboard/ProjectRowDetailDrawer.tsx": [
    { line: 134, from: "lg", to: "drawer" },
  ],
  "src/features/dashboard/DashboardSettingsDrawer.tsx": [
    { line: 22, from: "xl", to: "drawerWide" },
  ],

  // ------------------------------------------------------ chat thread/measure
  "src/features/chat/AssistantTurnBlock.tsx": [
    { line: 191, from: "[min(100%,42rem)]", to: "measure" },
  ],
  "src/features/chat/RunCardBlock.tsx": [
    { line: 267, from: "[min(100%,42rem)]", to: "measure" },
    { line: 477, from: "[min(100%,42rem)]", to: "measure" },
  ],
  "src/features/chat/SecretRegisterCard.tsx": [
    { line: 90, from: "[min(100%,42rem)]", to: "measure" },
  ],
  "src/features/chat/UserMessageBubble.tsx": [
    { line: 51, from: "[min(100%,42rem)]", to: "measure" },
  ],
  "src/pages/ChatPage.tsx": [
    { line: 3933, from: "[min(100%,42rem)]", to: "measure" },
    { line: 3828, from: "3xl", to: "thread" },
    { line: 3950, from: "3xl", to: "thread" },
    { line: 3369, from: "md", to: "measure" },
    { line: 3814, from: "md", to: "measure" },
    { line: 3815, from: "md", to: "measure" },
    { line: 3463, from: "[20rem]", to: "control" },
    { line: 3475, from: "[24rem]", to: "controlWide" },
  ],

  // ------------------------------------------------------- readable measure
  "src/pages/StudioPage.tsx": [
    { line: 242, from: "xl", to: "measure" },
    { line: 212, from: "2xl", to: "measure" },
  ],
  "src/features/dashboard/PublicGalleryShareView.tsx": [
    { line: 56, from: "2xl", to: "measure" },
    { line: 62, from: "[1600px]", to: "pageWide" },
  ],
  "src/pages/ProjectsPage.tsx": [
    { line: 159, from: "2xl", to: "measure" },
    { line: 156, from: "6xl", to: "pageWide" },
  ],
  "src/pages/admin/AdminTools.tsx": [
    { line: 556, from: "2xl", to: "measure" },
    { line: 565, from: "2xl", to: "measure" },
    { line: 554, from: "5xl", to: "pageWide" },
  ],
  "src/pages/admin/AdminAgentSubmissions.tsx": [
    { line: 169, from: "3xl", to: "measure" },
    { line: 167, from: "6xl", to: "pageWide" },
  ],
  "src/pages/admin/AdminAgents.tsx": [
    { line: 367, from: "3xl", to: "measure" },
    { line: 373, from: "3xl", to: "measure" },
    { line: 365, from: "6xl", to: "pageWide" },
  ],
  "src/pages/org/OrgGrantsPage.tsx": [
    { line: 147, from: "3xl", to: "measure" },
    { line: 138, from: "3xl", to: "pageNarrow" },
    { line: 145, from: "5xl", to: "pageWide" },
  ],
  "src/features/admin/benchmarks/BenchmarkRunOverridePanel.tsx": [
    { line: 156, from: "prose", to: "measure" },
  ],
  "src/pages/LegalPage.tsx": [{ line: 41, from: "3xl", to: "measure" }],
  "src/pages/DocsPage.tsx": [{ line: 17, from: "xl", to: "measure" }],

  // -------------------------------------------------------- page containers
  // A centred auth card and a centred wizard are gate panels, not pages — the
  // old narrow widths were right about the shape and wrong about the name.
  "src/pages/LoginPage.tsx": [{ line: 49, from: "sm", to: "dialog" }],
  "src/pages/SetupWizardPage.tsx": [{ line: 461, from: "lg", to: "dialog" }],
  "src/pages/admin/AdminScheduledJobs.tsx": [{ line: 7, from: "xl", to: "page" }],
  "src/pages/settings/NotificationsSettings.tsx": [
    { line: 126, from: "xl", to: "page" },
  ],
  "src/pages/settings/ProfileSettings.tsx": [{ line: 69, from: "xl", to: "page" }],
  "src/pages/HomePage.tsx": [{ line: 41, from: "2xl", to: "page" }],
  "src/pages/admin/interfaces/AdminInterfacesPageShell.tsx": [
    { line: 15, from: "2xl", to: "pageNarrow" },
    { line: 15, from: "4xl", to: "page" },
  ],
  "src/pages/settings/AgentSettings.tsx": [{ line: 170, from: "2xl", to: "page" }],
  "src/pages/DashboardPage.tsx": [
    { line: 1219, from: "md", to: "dialog" },
    { line: 2465, from: "md", to: "dialog" },
    { line: 2523, from: "md", to: "dialog" },
    { line: 2559, from: "md", to: "dialog" },
    { line: 1348, from: "3xl", to: "pageNarrow" },
    { line: 1163, from: "4xl", to: "page" },
    // The chat dock's two states. `lg:max-w-md` (448) against a `w-[min(400px,…)]`
    // was already inconsistent with its own width rule; the rail tokens make the
    // cap agree with the width instead of sitting 48px above it.
    { line: 1782, from: "[220px]", to: "railNarrow" },
    { line: 1783, from: "md", to: "rail" },
  ],
  "src/pages/admin/AdminDashboard.tsx": [
    { line: 58, from: "3xl", to: "pageNarrow" },
  ],
  "src/pages/org/OrgSetupPage.tsx": [{ line: 110, from: "3xl", to: "pageNarrow" }],
  "src/pages/org/OrgTeamPage.tsx": [{ line: 79, from: "4xl", to: "page" }],
  "src/pages/settings/FriendsSettings.tsx": [{ line: 236, from: "4xl", to: "page" }],
  "src/pages/settings/SharesSettings.tsx": [{ line: 440, from: "4xl", to: "page" }],
  "src/pages/admin/AdminHarnessConfig.tsx": [
    { line: 214, from: "5xl", to: "page" },
  ],
  "src/pages/org/OrgKnowledgePage.tsx": [{ line: 7, from: "5xl", to: "pageWide" }],

  // Footer and media-bar inner containers move onto the page grid. They sat at
  // 1024 while the page they belong to was 896, which is the misalignment the
  // concept calls out, not a deliberate wider bar.
  "src/features/media/MediaMiniPlayer.tsx": [
    { line: 91, from: "5xl", to: "page" },
    { line: 79, from: "md", to: "controlWide" },
  ],
  "src/features/media/MediaMiniPlayerPanel.tsx": [
    { line: 113, from: "5xl", to: "page" },
  ],
  "src/layout/AppLayout.tsx": [{ line: 281, from: "5xl", to: "page" }],
  "src/features/dashboard/DashboardOverviewPanel.tsx": [
    { line: 78, from: "5xl", to: "page" },
    { line: 68, from: "3xl", to: "pageNarrow" },
  ],
  "src/features/admin/operatorSettings/OperatorSettingsStickySave.tsx": [
    { line: 9, from: "4xl", to: "page" },
  ],
  "src/features/dashboard/BlockExpandModal.tsx": [
    { line: 52, from: "6xl", to: "pageWide" },
  ],

  // ---------------------------------------------------------- truncation caps
  "src/features/workspace/CodingWorkspacePanels.tsx": [
    { line: 373, from: "[5rem]", to: "chip" },
  ],
  "src/features/chat/TurnNavigator.tsx": [{ line: 91, from: "[8rem]", to: "chip" }],
  "src/features/chat/ContextInjectionGroup.tsx": [
    { line: 67, from: "[18rem]", to: "chipWide" },
  ],
  "src/features/chat/AgentRunningBadge.tsx": [
    { line: 54, from: "[min(100%,18rem)]", to: "chipWide" },
  ],
  "src/ui/Tooltip.tsx": [{ line: 324, from: "64", to: "chipWide" }],
};

import { create } from "zustand";

import type { GraphData } from "../api/types";
import type { Selection } from "../graph/GraphView";

/**
 * Canvas state that is not server state (TRD 6, "State management"). The root entity, hops
 * and layout live in the URL instead, so a view can be shared by link.
 */
interface CanvasState {
  selection: Selection | null;
  highlighted: string[];
  /** Nodes matching the "Find on graph" box; lit unless a hit preview is showing. */
  found: string[];
  /** Entities lit while the pointer rests on an analytics hit; wins over `highlighted`. */
  preview: string[];
  /** Graphs added by drill-down, merged on top of the neighborhood. */
  expansions: GraphData[];
  /** Which view `expansions` belong to (see `begin`), so they survive leaving the page. */
  owner: string | null;
  /** Query string of the last investigation, so the nav link can return to it. */
  search: string;
  setSearch: (s: string) => void;
  /** Start a view: a different key drops everything shown; the same key keeps it. */
  begin: (key: string) => void;
  /** Empty the workbench and forget the last investigation. */
  clear: () => void;
  /** Drop selection and highlights, keeping what is on the canvas. */
  clearView: () => void;
  setSelection: (s: Selection | null) => void;
  setHighlighted: (ids: string[]) => void;
  setPreview: (ids: string[]) => void;
  setFound: (ids: string[]) => void;
  addExpansion: (g: GraphData) => void;
}

export const useCanvas = create<CanvasState>((set) => ({
  selection: null,
  highlighted: [],
  preview: [],
  found: [],
  expansions: [],
  owner: null,
  search: "",
  setSearch: (search) => set({ search }),
  begin: (key) =>
    set((s) =>
      s.owner === key
        ? s
        : { owner: key, selection: null, highlighted: [], preview: [], found: [], expansions: [] },
    ),
  clear: () =>
    set({ owner: null, search: "", selection: null, highlighted: [], preview: [], found: [], expansions: [] }),
  clearView: () => set({ selection: null, highlighted: [], preview: [], found: [] }),
  setSelection: (selection) => set({ selection }),
  setHighlighted: (highlighted) => set({ highlighted }),
  setPreview: (preview) => set({ preview }),
  setFound: (found) => set({ found }),
  addExpansion: (g) => set((s) => ({ expansions: [...s.expansions, g] })),
}));

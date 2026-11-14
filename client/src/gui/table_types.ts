// The slice of the OpenSpiel GUI's frame contract (gui/src/contract) that the
// copied schnaps table reads. The schnaps-web server builds frames in this
// shape (server/schnaps_web/deal.py).

/** One legal action of the viewer: its id, label and the adapter's hint. */
export interface ActionEntry {
  readonly id: number;
  readonly label: string;
  readonly hint: unknown;
}

/** The adapter's view of the position and the viewer's hinted actions. */
export interface Presentation {
  readonly view: unknown;
  readonly actions: readonly ActionEntry[] | null;
}

/** A position as the server built it for one viewer. */
export interface Frame {
  /** The viewer's game seat, or null for a spectator. */
  readonly viewer: {readonly seat: number | null};
  /** The game seats' returns once the deal is over, else null. */
  readonly returns: readonly number[] | null;
}

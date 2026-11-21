// Every string the site shows, in English, German and Italian, and the
// small lookup that picks one.
//
// English is the base: a string missing in another language falls back to
// it. Italian is preselected. The language belongs to a table (chosen in the
// lobby when the table is started); the lobby itself shows the language
// picked there.
//
// The server sends language-neutral data: card codes, action ids, contract
// names ("Lomt"), bids ("Pass") and English error messages. This file turns
// all of them into the reader's language (gameTerms below, serverError).
//
// To add a string: add a key to STRINGS with en, de and it, then show it with
// t(lang, 'key') (or useT() in a component). `{name}` marks a parameter:
// t(lang, 'seatN', {n: 2}). The tests (strings.test.ts) check that every
// language has the same parameters.
//
// No React here, so `node --test` can run the tests without a bundler.

import type {Rank, Suit} from '../gui/cards/card.ts';

export type Lang = 'it' | 'de' | 'en';

/** The languages in the picker's order. */
export const LANGS: readonly Lang[] = ['it', 'de', 'en'];

/** The preselected language. */
export const DEFAULT_LANG: Lang = 'it';

/** Each language by its own name, as the picker shows it. */
export const LANG_NAMES: Readonly<Record<Lang, string>> = {
  it: 'Italiano',
  de: 'Deutsch',
  en: 'English',
};

interface Entry {
  readonly en: string;
  readonly de: string;
  readonly it: string;
}

export const STRINGS = {
  // Lobby.
  language: {en: 'Language', de: 'Sprache', it: 'Lingua'},
  siteTitle: {en: 'Schnaps', de: 'Schnaps', it: 'Schnaps'},
  watchingTitle: {
    en: 'watching, all cards shown',
    de: 'Zuschauen, alle Karten offen',
    it: 'spettatore, tutte le carte scoperte',
  },
  yourNickname: {en: 'Your nickname', de: 'Dein Spitzname', it: 'Il tuo soprannome'},
  nicknameExample: {en: 'e.g. Anna', de: 'z. B. Anna', it: 'es. Anna'},
  startATable: {en: 'Start a table', de: 'Tisch eröffnen', it: 'Apri un tavolo'},
  tableName: {en: 'Table name', de: 'Tischname', it: 'Nome del tavolo'},
  tableNameExample: {en: 'Stammtisch', de: 'Stammtisch', it: 'Stammtisch'},
  yourSeat: {en: 'Your seat', de: 'Dein Platz', it: 'Il tuo posto'},
  tableLanguage: {
    en: 'Table language',
    de: 'Sprache am Tisch',
    it: 'Lingua del tavolo',
  },
  startTable: {en: 'Start table', de: 'Tisch eröffnen', it: 'Apri tavolo'},
  defaultTableName: {en: "{player}'s table", de: 'Tisch von {player}', it: 'Tavolo di {player}'},
  serverUnreachable: {
    en: 'The server is not reachable.',
    de: 'Der Server ist nicht erreichbar.',
    it: 'Il server non è raggiungibile.',
  },
  enterNicknameFirst: {
    en: 'Enter your nickname first.',
    de: 'Gib zuerst deinen Spitznamen ein.',
    it: 'Inserisci prima il tuo soprannome.',
  },
  tables: {en: 'Tables', de: 'Tische', it: 'Tavoli'},
  loading: {en: 'Loading…', de: 'Lädt…', it: 'Caricamento…'},
  noTables: {en: 'No tables yet.', de: 'Noch keine Tische.', it: 'Ancora nessun tavolo.'},
  noTablesStartOne: {
    en: 'No tables yet. Start one above.',
    de: 'Noch keine Tische. Eröffne oben einen.',
    it: 'Ancora nessun tavolo. Aprine uno qui sopra.',
  },
  setsCount: {en: '{n} sets', de: '{n} Sätze', it: '{n} set'},
  setsCountOne: {en: '1 set', de: '1 Satz', it: '1 set'},
  sitHere: {en: 'Sit here', de: 'Hier setzen', it: 'Siediti qui'},
  botSuffix: {en: ' (bot)', de: ' (Bot)', it: ' (bot)'},
  offlineSuffix: {en: ' (offline)', de: ' (offline)', it: ' (offline)'},
  backToMySeat: {en: 'Back to my seat', de: 'Zurück zu meinem Platz', it: 'Torna al mio posto'},
  watch: {en: 'Watch', de: 'Zuschauen', it: 'Guarda'},

  // Seats, pairs and phases (table/labels.ts).
  seatN: {en: 'Seat {n}', de: 'Platz {n}', it: 'Posto {n}'},
  seatChoice: {
    en: 'Seat {n} (partner of seat {m})',
    de: 'Platz {n} (Partner von Platz {m})',
    it: 'Posto {n} (compagno del posto {m})',
  },
  pairOf: {en: '{a} & {b}', de: '{a} & {b}', it: '{a} & {b}'},
  phaseOpen: {en: 'Waiting for players', de: 'Warten auf Spieler', it: 'In attesa di giocatori'},
  phasePlaying: {en: 'Playing', de: 'Läuft', it: 'In gioco'},
  phaseDealOver: {en: 'Deal over', de: 'Spiel vorbei', it: 'Mano finita'},
  phaseMatchOver: {en: 'Match over', de: 'Partie vorbei', it: 'Partita finita'},
  phaseClosed: {en: 'Closed', de: 'Geschlossen', it: 'Chiuso'},

  // The table page.
  tableClosed: {
    en: 'This table is closed.',
    de: 'Dieser Tisch ist geschlossen.',
    it: 'Questo tavolo è chiuso.',
  },
  backToLobby: {en: 'Back to the lobby', de: 'Zurück zur Lobby', it: 'Torna alla sala'},
  connecting: {en: 'Connecting…', de: 'Verbinde…', it: 'Connessione…'},
  nicknamePrompt: {en: 'Your nickname?', de: 'Dein Spitzname?', it: 'Il tuo soprannome?'},
  lobbyLink: {en: '← Lobby', de: '← Lobby', it: '← Sala'},
  watchingBadge: {
    en: 'watching · all cards shown',
    de: 'Zuschauen · alle Karten offen',
    it: 'spettatore · tutte le carte scoperte',
  },
  reconnecting: {en: 'reconnecting…', de: 'verbinde neu…', it: 'riconnessione…'},
  rotateHint: {
    en: 'Turn your phone sideways to see the whole table.',
    de: 'Dreh das Handy quer, dann siehst du den ganzen Tisch.',
    it: 'Gira il telefono in orizzontale per vedere tutto il tavolo.',
  },
  startMatch: {en: 'Start match', de: 'Partie starten', it: 'Inizia la partita'},
  newMatch: {en: 'New match', de: 'Neue Partie', it: 'Nuova partita'},
  closeTableConfirm: {
    en: 'Close this table for everyone?',
    de: 'Diesen Tisch für alle schließen?',
    it: 'Chiudere questo tavolo per tutti?',
  },
  closeTable: {en: 'Close table', de: 'Tisch schließen', it: 'Chiudi tavolo'},
  fillSeats: {
    en: 'Fill the empty seats (players or bots), then start the match.',
    de: 'Besetze die freien Plätze (Spieler oder Bots), dann starte die Partie.',
    it: 'Occupa i posti liberi (giocatori o bot), poi inizia la partita.',
  },
  waitingForStart: {
    en: 'Waiting for the table to start.',
    de: 'Warten, bis der Tisch startet.',
    it: 'In attesa che il tavolo inizi.',
  },
  nameOffline: {en: '{name} · offline', de: '{name} · offline', it: '{name} · offline'},
  score: {en: 'Score', de: 'Stand', it: 'Punteggio'},
  setOfThree: {en: 'Set {n} · best of 3', de: 'Satz {n} · 2 aus 3', it: 'Set {n} · al meglio dei 3'},
  pair: {en: 'Pair', de: 'Paar', it: 'Coppia'},
  pointsToGo: {en: 'Points to go', de: 'Noch zu machen', it: 'Punti mancanti'},
  sets: {en: 'Sets', de: 'Sätze', it: 'Set'},
  dealerIs: {en: 'Dealer: {name}', de: 'Geber: {name}', it: 'Mazziere: {name}'},
  seats: {en: 'Seats', de: 'Plätze', it: 'Posti'},
  empty: {en: 'empty', de: 'frei', it: 'libero'},
  online: {en: 'online', de: 'online', it: 'online'},
  offline: {en: 'offline', de: 'offline', it: 'offline'},
  botOfKind: {en: '({label} bot)', de: '({label}-Bot)', it: '(bot {label})'},
  you: {en: '(you)', de: '(du)', it: '(tu)'},
  addBot: {en: '+ {label}', de: '+ {label}', it: '+ {label}'},
  removeBot: {en: 'Remove bot', de: 'Bot entfernen', it: 'Togli il bot'},
  leave: {en: 'Leave', de: 'Aufstehen', it: 'Alzati'},
  botBasic: {en: 'Basic', de: 'Basis', it: 'Base'},
  botLarge: {en: 'Large', de: 'Groß', it: 'Grande'},
  winPoint: {en: '{pair} win 1 point', de: '{pair} gewinnen 1 Punkt', it: '{pair} vincono 1 punto'},
  winPoints: {
    en: '{pair} win {n} points',
    de: '{pair} gewinnen {n} Punkte',
    it: '{pair} vincono {n} punti',
  },
  byDeclarer: {en: ' by {name}', de: ' von {name}', it: ' di {name}'},
  toGo: {en: 'To go:', de: 'Noch:', it: 'Mancano:'},
  setTo: {en: 'Set {n} to {pair}!', de: 'Satz {n} an {pair}!', it: 'Set {n} a {pair}!'},
  matchTo: {en: 'Match to {pair}!', de: 'Partie an {pair}!', it: 'Partita a {pair}!'},
  nextDeal: {
    en: 'Next deal in a moment…',
    de: 'Gleich kommt das nächste Spiel…',
    it: 'Tra poco la prossima mano…',
  },
  waitButton: {en: 'Wait', de: 'Warten', it: 'Aspetta'},
  waitRelease: {en: 'Continue', de: 'Weiter', it: 'Continua'},
  waitingFor: {
    en: 'The next deal waits for {names}',
    de: 'Das nächste Spiel wartet auf {names}',
    it: 'La prossima mano aspetta {names}',
  },
  scoreSheet: {en: 'Score sheet', de: 'Spielliste', it: 'Segnapunti'},
  colNumber: {en: '#', de: '#', it: '#'},
  colSet: {en: 'Set', de: 'Satz', it: 'Set'},
  colDealer: {en: 'Dealer', de: 'Geber', it: 'Mazziere'},
  colContract: {en: 'Contract', de: 'Spiel', it: 'Gioco'},
  colDeclarer: {en: 'Declarer', de: 'Ansager', it: 'Dichiarante'},
  colWonBy: {en: 'Won by', de: 'Gewonnen von', it: 'Vinto da'},
  colPoints: {en: 'Pts', de: 'Pkt', it: 'Pti'},

  // The card table (gui/games/schnaps).
  playerN: {en: 'Player {n}', de: 'Spieler {n}', it: 'Giocatore {n}'},
  teamOf: {en: '{a} + {b}', de: '{a} + {b}', it: '{a} + {b}'},
  dealing: {en: 'Dealing…', de: 'Es wird gegeben…', it: 'Si distribuisce…'},
  choosesTrump: {
    en: '{name} chooses trump from the first three cards',
    de: '{name} wählt Trumpf aus den ersten drei Karten',
    it: '{name} sceglie la briscola dalle prime tre carte',
  },
  bidding: {
    en: 'Bidding: {name} calls, flecks or passes',
    de: 'Ansagen: {name} sagt an, fleckt oder sagt weiter',
    it: 'Dichiarazioni: {name} chiama, flecka o dice via',
  },
  toPlay: {en: '{name} to play', de: '{name} spielt aus', it: 'Tocca a {name}'},
  dealInfo: {en: 'Deal', de: 'Spiel', it: 'Mano'},
  trump: {en: 'Trump', de: 'Trumpf', it: 'Briscola'},
  trumpSuit: {en: 'trump {suit}', de: 'Trumpf {suit}', it: 'briscola {suit}'},
  contract: {en: 'Contract', de: 'Spiel', it: 'Gioco'},
  ptsTricks: {
    en: '{pts} pts · {tricks} tricks',
    de: '{pts} Pkt · {tricks} Stiche',
    it: '{pts} pti · {tricks} prese',
  },
  trick: {en: 'Trick', de: 'Stich', it: 'Presa'},
  lastTrickWon: {
    en: 'Last trick: {name} won',
    de: 'Letzter Stich: {name}',
    it: 'Ultima presa: {name}',
  },
  moves: {en: 'Moves', de: 'Züge', it: 'Mosse'},
  faceDownCard: {en: 'Face-down card', de: 'Verdeckte Karte', it: 'Carta coperta'},
  declareLead: {
    en: 'Declare {points}, lead {card}',
    de: '{points} ansagen, {card} ausspielen',
    it: 'Accusa {points}, gioca {card}',
  },
  trumpChoice: {en: 'Trump: {suit}', de: 'Trumpf: {suit}', it: 'Briscola: {suit}'},

  // Game terms. Italian and English keep the German names, except the
  // Italian ranks and Pass (the user's choice).
  suitH: {en: 'Herz', de: 'Herz', it: 'Herz'},
  suitD: {en: 'Caro', de: 'Caro', it: 'Caro'},
  suitS: {en: 'Pik', de: 'Pik', it: 'Pik'},
  suitC: {en: 'Kreuz', de: 'Kreuz', it: 'Kreuz'},
  rankJ: {en: 'Unter', de: 'Unter', it: 'Nižek'},
  rankQ: {en: 'Ober', de: 'Ober', it: 'Cavallo'},
  rankK: {en: 'König', de: 'König', it: 'Re'},
  rankT: {en: 'Zehn', de: 'Zehn', it: 'Dieci'},
  rankA: {en: 'As', de: 'As', it: 'Asso'},
  // A card's corner index (only drawn when a card has no picture).
  indexJ: {en: 'U', de: 'U', it: 'N'},
  indexQ: {en: 'O', de: 'O', it: 'C'},
  indexK: {en: 'K', de: 'K', it: 'R'},
  indexT: {en: '10', de: '10', it: '10'},
  indexA: {en: 'A', de: 'A', it: 'A'},
  cardName: {en: '{suit} {rank}', de: '{suit} {rank}', it: '{rank} di {suit}'},
  bidPass: {en: 'Pass', de: 'Weiter', it: 'Via'},
  bidFleck: {en: 'Fleck', de: 'Fleck', it: 'Fleck'},
  contractNormal: {en: 'Normal', de: 'Normal', it: 'Normal'},
  contractSchnapser: {en: 'Schnapser', de: 'Schnapser', it: 'Schnapser'},
  contractLomt: {en: 'Lomt', de: 'Lomt', it: 'Lomt'},
  contractBauern: {en: 'Bauern', de: 'Bauern', it: 'Bauern'},
  contractJodler: {en: 'Jodler', de: 'Jodler', it: 'Jodler'},
  contractHermort: {en: 'Hermort', de: 'Hermort', it: 'Hermort'},

  // The server's error messages (matched by serverError below; the English
  // text must equal what the server sends, `{x}` matching any word).
  errNoSuchTable: {en: 'no such table', de: 'Diesen Tisch gibt es nicht', it: 'Tavolo inesistente'},
  errTooManyTables: {
    en: 'too many tables; close one first',
    de: 'Zu viele Tische; schließe zuerst einen',
    it: 'Troppi tavoli; chiudine prima uno',
  },
  errNicknameRequired: {
    en: 'a nickname is required',
    de: 'Ein Spitzname ist nötig',
    it: 'Serve un soprannome',
  },
  errTableNameRequired: {
    en: 'a table name is required',
    de: 'Ein Tischname ist nötig',
    it: 'Serve un nome per il tavolo',
  },
  errNicknameTooLong: {
    en: 'the nickname is longer than {n} characters',
    de: 'Der Spitzname ist länger als {n} Zeichen',
    it: 'Il soprannome supera {n} caratteri',
  },
  errTableNameTooLong: {
    en: 'the table name is longer than {n} characters',
    de: 'Der Tischname ist länger als {n} Zeichen',
    it: 'Il nome del tavolo supera {n} caratteri',
  },
  errSeatTaken: {en: 'seat {n} is taken', de: 'Platz {n} ist besetzt', it: 'Il posto {n} è occupato'},
  errSeatHasPlayer: {
    en: 'seat {n} has a player',
    de: 'Auf Platz {n} sitzt ein Spieler',
    it: 'Al posto {n} siede un giocatore',
  },
  errMatchRunning: {
    en: 'a match is already running',
    de: 'Eine Partie läuft schon',
    it: 'Una partita è già in corso',
  },
  errFillSeats: {
    en: 'every seat must be filled first',
    de: 'Zuerst müssen alle Plätze besetzt sein',
    it: 'Prima vanno occupati tutti i posti',
  },
  errNoDeal: {en: 'no deal is in progress', de: 'Es läuft kein Spiel', it: 'Nessuna mano in corso'},
  errCreatorOnly: {
    en: "only the table's creator may do that",
    de: 'Das darf nur, wer den Tisch eröffnet hat',
    it: 'Può farlo solo chi ha aperto il tavolo',
  },
  errMayNotEmpty: {
    en: 'you may not empty that seat',
    de: 'Du darfst diesen Platz nicht räumen',
    it: 'Non puoi liberare quel posto',
  },
  errNoSeat: {
    en: 'you have no seat at this table',
    de: 'Du hast keinen Platz an diesem Tisch',
    it: 'Non hai un posto a questo tavolo',
  },
  errDealOver: {en: 'the deal is over', de: 'Das Spiel ist vorbei', it: 'La mano è finita'},
  errNotYourTurn: {
    en: "it is not seat {n}'s turn",
    de: 'Platz {n} ist nicht am Zug',
    it: 'Non tocca al posto {n}',
  },
  errNotLegal: {
    en: 'action {n} is not legal',
    de: 'Zug {n} ist nicht erlaubt',
    it: 'La mossa {n} non è ammessa',
  },
  errCannotResign: {
    en: 'you cannot resign now',
    de: 'Aufgeben geht jetzt nicht',
    it: 'Ora non puoi abbandonare',
  },
  errShowOnlyInPlay: {
    en: 'you can only show your cards during the card play',
    de: 'Zeigen geht nur während des Ausspielens',
    it: 'Puoi mostrare le carte solo durante il gioco delle carte',
  },
  errAlreadyShown: {
    en: 'your cards are already shown',
    de: 'Deine Karten sind schon aufgedeckt',
    it: 'Le tue carte sono già scoperte',
  },
  errNoDealEnded: {
    en: 'no deal has just ended',
    de: 'Gerade ist kein Spiel zu Ende gegangen',
    it: 'Nessuna mano è appena finita',
  },
  errWaitBool: {
    en: 'wait is true or false',
    de: 'Warten ist ja oder nein',
    it: 'Aspetta è sì o no',
  },
  errThrowKind: {
    en: 'a throw is one of {kinds}',
    de: 'Unbekannter Wurf (erlaubt: {kinds})',
    it: 'Giocata sconosciuta (ammesse: {kinds})',
  },

  // cardthrowup (table/throw_bar.tsx, docs/cardthrowup.md): Show (the hand
  // open to the two opponents) and Resign.
  throwBar: {en: 'Throw your cards', de: 'Karten hinlegen', it: 'Scopri le carte'},
  throwResign: {en: 'Resign', de: 'Aufgeben', it: 'Abbandona'},
  throwShow: {en: 'Show', de: 'Zeigen', it: 'Mostra'},
  throwResignConfirm: {
    en: 'Resign? Your side loses this deal.',
    de: 'Aufgeben? Deine Seite verliert dieses Spiel.',
    it: 'Abbandonare? La tua coppia perde questa mano.',
  },
  throwShowConfirm: {
    en: 'Show your cards to the opponents? They stay open to them for this deal.',
    de: 'Den Gegnern die Karten zeigen? Sie bleiben für dieses Spiel offen.',
    it: 'Mostrare le carte agli avversari? Restano scoperte per questa mano.',
  },
  throwYes: {en: 'Yes', de: 'Ja', it: 'Sì'},
  throwCancel: {en: 'Cancel', de: 'Abbrechen', it: 'Annulla'},
  throwResigns: {en: '{name} resigns', de: '{name} gibt auf', it: '{name} abbandona'},
  throwShows: {
    en: '{name} shows their cards to the opponents',
    de: '{name} zeigt den Gegnern die Karten',
    it: '{name} mostra le carte agli avversari',
  },
  sheetResigned: {en: 'resigned', de: 'aufgegeben', it: 'abbandono'},
} as const satisfies Record<string, Entry>;

export type Key = keyof typeof STRINGS;

export type Params = Readonly<Record<string, string | number>>;

/** `lang`'s text for `key`, its `{name}` parameters filled in. */
export function t(lang: Lang, key: Key, params: Params = {}): string {
  const entry: Entry = STRINGS[key];
  const text = entry[lang] || entry.en;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = params[name];
    return value === undefined ? whole : String(value);
  });
}

/** `lang` if it is one of LANGS, else DEFAULT_LANG. */
export function asLang(value: unknown): Lang {
  return LANGS.includes(value as Lang) ? (value as Lang) : DEFAULT_LANG;
}

// ---- Game terms: what the server sends, in the reader's language. ----

const SUIT_KEYS: Readonly<Record<Suit, Key>> = {
  h: 'suitH',
  d: 'suitD',
  s: 'suitS',
  c: 'suitC',
};

const RANK_KEYS: Partial<Readonly<Record<Rank, Key>>> = {
  J: 'rankJ',
  Q: 'rankQ',
  K: 'rankK',
  T: 'rankT',
  A: 'rankA',
};

const INDEX_KEYS: Partial<Readonly<Record<Rank, Key>>> = {
  J: 'indexJ',
  Q: 'indexQ',
  K: 'indexK',
  T: 'indexT',
  A: 'indexA',
};

/** A suit's name: "Herz". */
export function suitName(lang: Lang, suit: Suit): string {
  return t(lang, SUIT_KEYS[suit]);
}

/** A rank's name: "Ober" (Italian "Cavallo"). */
export function rankName(lang: Lang, rank: Rank): string {
  const key = RANK_KEYS[rank];
  return key === undefined ? rank : t(lang, key);
}

/** A rank's corner index: "O" (Italian "C"). */
export function rankIndex(lang: Lang, rank: Rank): string {
  const key = INDEX_KEYS[rank];
  return key === undefined ? rank : t(lang, key);
}

/** A card's name: "Herz König" (Italian "Re di Herz"). */
export function cardName(lang: Lang, rank: Rank, suit: Suit): string {
  return t(lang, 'cardName', {suit: suitName(lang, suit), rank: rankName(lang, rank)});
}

/** The game's contracts as the server names them, in action order (34..38). */
export const CALLS = ['Schnapser', 'Lomt', 'Bauern', 'Jodler', 'Hermort'] as const;

const CONTRACT_KEYS: Readonly<Record<string, Key>> = {
  Normal: 'contractNormal',
  Schnapser: 'contractSchnapser',
  Lomt: 'contractLomt',
  Bauern: 'contractBauern',
  Jodler: 'contractJodler',
  Hermort: 'contractHermort',
};

/** A contract the server names ("Normal", "Lomt"), in `lang`. */
export function contractName(lang: Lang, name: string): string {
  const key = CONTRACT_KEYS[name];
  return key === undefined ? name : t(lang, key);
}

/** A bid the server names ("Pass", "Fleck", a contract), in `lang`. */
export function bidText(lang: Lang, bid: string): string {
  if (bid === 'Pass') return t(lang, 'bidPass');
  if (bid === 'Fleck') return t(lang, 'bidFleck');
  return contractName(lang, bid);
}

const FIRST_DECLARE = 20;
const FIRST_TRUMP = 28;
const PASS = 32;
const FLECK = 33;
const FIRST_CALL = 34;
const TRUMP_SUITS: readonly Suit[] = ['h', 'd', 's', 'c'];

/**
 * A move button's text, from the action id (server: game/view.py).
 *
 * `declared` is the card a 20/40 leads (its hint's "declare" code, e.g.
 * "Kh"), `trump` the deal's trump. Anything unknown keeps the server's text.
 */
export function actionText(
  lang: Lang,
  action: number,
  serverText: string,
  declared: {readonly rank: Rank; readonly suit: Suit} | null,
  trump: Suit | null,
): string {
  if (action >= FIRST_DECLARE && action < FIRST_TRUMP && declared !== null) {
    return t(lang, 'declareLead', {
      points: declared.suit === trump ? 40 : 20,
      card: cardName(lang, declared.rank, declared.suit),
    });
  }
  if (action >= FIRST_TRUMP && action < PASS) {
    const suit = TRUMP_SUITS[action - FIRST_TRUMP];
    if (suit !== undefined) return t(lang, 'trumpChoice', {suit: suitName(lang, suit)});
  }
  if (action === PASS) return t(lang, 'bidPass');
  if (action === FLECK) return t(lang, 'bidFleck');
  const call = CALLS[action - FIRST_CALL];
  if (call !== undefined) return contractName(lang, call);
  return serverText;
}

const BOT_KEYS: Readonly<Record<string, Key>> = {
  Basic: 'botBasic',
  Large: 'botLarge',
};

/** A bot's kind as the server labels it ("Basic", "Large"), in `lang`. */
export function botLabel(lang: Lang, label: string): string {
  const key = BOT_KEYS[label];
  return key === undefined ? label : t(lang, key);
}

// ---- Server error messages. ----

const ERROR_KEYS: readonly Key[] = (Object.keys(STRINGS) as Key[]).filter(k =>
  k.startsWith('err'),
);

function errorPattern(english: string): RegExp {
  const parts = english.split(/\{\w+\}/);
  const escaped = parts.map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return new RegExp(`^${escaped.join('(.+?)')}$`);
}

const ERROR_PATTERNS: ReadonlyArray<{readonly key: Key; readonly re: RegExp; readonly names: string[]}> =
  ERROR_KEYS.map(key => {
    const english = STRINGS[key].en;
    const names = [...english.matchAll(/\{(\w+)\}/g)].map(m => m[1] ?? '');
    return {key, re: errorPattern(english), names};
  });

// The server counts table seats from 0, the site shows them from 1.
const TABLE_SEAT_ERRORS: ReadonlySet<Key> = new Set<Key>(['errSeatTaken', 'errSeatHasPlayer']);

/** An error message from the server, in `lang` (unknown ones stay English). */
export function serverError(lang: Lang, message: string): string {
  for (const {key, re, names} of ERROR_PATTERNS) {
    const match = re.exec(message);
    if (match === null) continue;
    const params: Record<string, string> = {};
    names.forEach((name, i) => {
      const value = match[i + 1] ?? '';
      params[name] =
        TABLE_SEAT_ERRORS.has(key) && /^\d+$/.test(value) ? String(Number(value) + 1) : value;
    });
    return t(lang, key, params);
  }
  return message;
}

// The language in React: the table's (or the lobby picker's) language for
// every component below it, and the lobby's choice kept in the browser.

import {createContext, useContext} from 'react';

import {asLang, DEFAULT_LANG, type Key, type Lang, type Params, t} from './strings.ts';

/** The language the components below read (a table's, or the lobby's). */
export const LangContext = createContext<Lang>(DEFAULT_LANG);

/** The current language. */
export function useLang(): Lang {
  return useContext(LangContext);
}

/** t() in the current language: `const tr = useT(); tr('seats')`. */
export function useT(): (key: Key, params?: Params) => string {
  const lang = useLang();
  return (key, params) => t(lang, key, params);
}

const LANG_KEY = 'schnaps.lang';

/** The language last picked in the lobby (Italian until one is picked). */
export function storedLang(): Lang {
  try {
    return asLang(localStorage.getItem(LANG_KEY));
  } catch {
    return DEFAULT_LANG;
  }
}

export function storeLang(lang: Lang): void {
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    // Storage unavailable: the choice lasts as long as the page.
  }
}

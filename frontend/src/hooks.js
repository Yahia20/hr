import { useEffect, useState } from "react";

export function useDebouncedValue(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const h = (e) => setMatches(e.matches);
    mq.addEventListener("change", h);
    setMatches(mq.matches);
    return () => mq.removeEventListener("change", h);
  }, [query]);
  return matches;
}

export function useLocalStorage(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw !== null ? JSON.parse(raw) : initial;
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage full/blocked — theme/lang simply won't persist */
    }
  }, [key, value]);
  return [value, setValue];
}

/** Global single-key shortcuts; suppressed while typing in a field or when a
 *  dialog wants exclusive keyboard input. map: { key: () => void } */
export function useHotkeys(map, enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    const h = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = (e.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) return;
      const fn = map[e.key];
      if (fn) {
        e.preventDefault();
        fn();
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [map, enabled]);
}

/** Pagination over a client-side array. */
export function usePagination(items, pageSize = 10) {
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const current = Math.min(page, pages);
  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);
  return {
    page: current,
    pages,
    total: items.length,
    setPage,
    slice: items.slice((current - 1) * pageSize, current * pageSize),
    from: items.length === 0 ? 0 : (current - 1) * pageSize + 1,
    to: Math.min(current * pageSize, items.length),
  };
}

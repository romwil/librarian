import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import WorkPeek from "./WorkPeek.jsx";

const PeekContext = createContext({ openWork() {}, closeWork() {}, isOpen: false });

export function useWorkPeek() {
  return useContext(PeekContext);
}

export function WorkPeekProvider({ children }) {
  const [work, setWork] = useState(null);
  const returnFocus = useRef(null);

  const openWork = useCallback((next, options = {}) => {
    if (!next) return false;
    if (options.triggerEl) returnFocus.current = options.triggerEl;
    setWork(next);
    return true;
  }, []);

  const closeWork = useCallback(() => {
    setWork(null);
    returnFocus.current?.focus?.();
  }, []);

  const value = useMemo(
    () => ({ openWork, closeWork, isOpen: Boolean(work) }),
    [openWork, closeWork, work],
  );

  return (
    <PeekContext.Provider value={value}>
      {children}
      <WorkPeek work={work} onClose={closeWork} />
    </PeekContext.Provider>
  );
}

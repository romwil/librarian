import AudiobookPlayer from "./AudiobookPlayer.jsx";
import Reader from "./Reader.jsx";
import { workCanListen, workCanRead } from "../hooks/useWorkRooms.js";

/** Reading room over a work page, when a readable volume is open. */
export function WorkReaderShell({ rooms, data }) {
  if (!rooms.reading || !workCanRead(data)) return null;
  return (
    <Reader
      work={data.work}
      files={data.files}
      fileId={rooms.readingFileId}
      progress={data.progress}
      onClose={rooms.closeReader}
    />
  );
}

/** Listening room over a work page, when an audiobook is open. */
export function WorkListenShell({ rooms, data, setData }) {
  if (!rooms.listening || !workCanListen(data)) return null;
  return (
    <AudiobookPlayer
      work={data.work}
      files={data.files}
      fileId={rooms.listeningFileId}
      progress={data.progress}
      player={data.listen?.player || null}
      playerNote={data.listen?.player_note || ""}
      remember={data.listen?.remember || ""}
      onClose={rooms.closeListen}
      onProgress={(row) => setData((prev) => (prev ? { ...prev, progress: row } : prev))}
    />
  );
}

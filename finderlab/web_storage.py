"""Bounded active-workspace admission and intact finalized-capture archival.

No deletion, raw capture edits, networking or printer operations. Archive stays
inside the persistent volume, but has a separate finite budget.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone

ARCHIVE_BYTES = 2 * 1024**3
ARCHIVE_ENTRIES = 16384
ACTIVE_ENTRIES = 4096


class StorageError(ValueError):
    pass


def _scan_error(exc):
    raise StorageError('Cannot inspect storage: '+str(exc))


def measure(folder, *, exclude_archive=False, limit_entries=ARCHIVE_ENTRIES):
    total=count=0
    if not folder.exists():return 0,0
    if folder.is_symlink() or not folder.is_dir():raise StorageError('Unexpected storage directory/symlink')
    for directory,dirs,files in os.walk(folder,followlinks=False,onerror=_scan_error):
        for name in dirs+files:
            path=Path(directory)/name
            if path.is_symlink() or not (path.is_file() or path.is_dir()):raise StorageError('Unexpected symlink/special file in web storage')
            if exclude_archive and Path(directory)==folder and name=='archive':continue
            count+=1
            if path.is_file():total+=path.stat().st_size
            if count>limit_entries:raise StorageError('Storage entry scan bound reached; archive records externally')
        if exclude_archive and Path(directory)==folder:dirs[:]=[d for d in dirs if d!='archive']
    return total,count


def admit(folder, reserve, limit, *, auto_archive=True, protected=()):
    """Archive oldest complete inactive recordings only when admission needs it."""
    folder=Path(folder);total,count=measure(folder,exclude_archive=True)
    fits=lambda:total+reserve<=limit and count<=ACTIVE_ENTRIES
    if fits():return total,count,[]
    moved=[]
    if not auto_archive:return total,count,moved
    protected={Path(p).resolve() for p in protected if p}
    captures=folder/'captures';candidates=[]
    if captures.is_dir():
        for directory in captures.iterdir():
            if not directory.is_dir() or directory.resolve() in protected:continue
            manifest=directory/'manifest.json'
            if not manifest.is_file() or not 0<manifest.stat().st_size<=1024*1024:continue
            try:
                data=json.loads(manifest.read_bytes())
                ended=data.get('ended_utc')
                if (data.get('complete') is not True or data.get('capture_id')!=directory.name
                        or not isinstance(ended,str) or not ended
                        or any(s.get('closed') is not True for s in data.get('sessions',[]))):continue
                when=datetime.fromisoformat(ended)
                if when.tzinfo is None:continue
            except (ValueError,TypeError,AttributeError,RecursionError):continue
            candidates.append((when,directory))
    if not candidates:return total,count,moved
    archive=folder/'archive';used,entries=measure(archive)
    for _,source in sorted(candidates):
        if fits():break
        size,n=measure(source);target=archive/'captures'/source.name
        if target.exists():continue  # Never overwrite or merge archived evidence.
        record={'utc':datetime.now(timezone.utc).isoformat(),'capture_id':source.name,
                'from':str(source.relative_to(folder)),'to':str(target.relative_to(folder)),'bytes':size}
        encoded=(json.dumps(record,separators=(',',':'))+'\n').encode()
        if used+size+len(encoded)>ARCHIVE_BYTES or entries+n+4>ARCHIVE_ENTRIES:
            raise StorageError('Automatic archive budget reached (2GiB/16384 entries); move old archived records to other storage manually. Nothing deleted.')
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        try:
            source.rename(target)  # Same persistent volume: atomic intact-directory move.
            with (archive/'index.jsonl').open('ab') as index:index.write(encoded)
        except OSError as exc:
            raise StorageError('Cannot archive finalized capture; inspect archive/index and filesystem: '+str(exc)) from exc
        total-=size;count-=n+1;used+=size+len(encoded);entries+=n+1;moved.append(record)
    return total,count,moved

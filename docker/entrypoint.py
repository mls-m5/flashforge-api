#!/usr/bin/env python3
"""Fixed container configuration -> existing CLI argv; no shell/discovery/probes."""
import ipaddress
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from finderlab.web_access import validate_listener


def boolean(env,key,default=False):
    value=env.get(key,str(default)).strip().lower()
    if value in ('1','true','yes','on'):return True
    if value in ('0','false','no','off',''):return False
    raise ValueError(key+' must be true or false')


def integer(env,key,default,low,high):
    raw=env.get(key,str(default))
    if not raw.isascii() or not raw.isdecimal() or len(raw)>10:raise ValueError(key+' must be a bounded integer')
    result=int(raw)
    if not low<=result<=high:raise ValueError(f'{key} must be in [{low},{high}]')
    return result


def command(env, *, profile_dir=Path('/profiles'), orca=Path('/opt/orca/AppRun')):
    service=env.get('FINDER_SERVICE','web')
    if service=='proxy':
        raw=env.get('FINDER_PRINTER_HOST','').strip()
        if not raw:raise ValueError('Set FINDER_PRINTER_HOST explicitly before starting the printer profile; no printer is discovered')
        target=ipaddress.ip_address(raw)
        if target.is_unspecified or target.is_multicast:raise ValueError('Printer target must be a unicast literal IP')
        if not target.is_loopback and not boolean(env,'FINDER_ALLOW_HARDWARE'):
            raise ValueError('Bundled proxy to hardware requires FINDER_ALLOW_HARDWARE=true and deliberate operator selection')
        port=integer(env,'FINDER_PROXY_PORT',9000,1,65535)
        target_port=integer(env,'FINDER_PRINTER_PORT',8899,1,65535)
        if target.is_loopback and port==target_port:raise ValueError('Refusing a proxy loop to its own listener')
        return ['-m','finderlab','proxy','--host','127.0.0.1','--port',str(port),
                '--target-host',str(target),'--target-port',str(target_port),
                '--capture-dir','/app/proxy-captures']
    if service!='web':raise ValueError('FINDER_SERVICE must be web or proxy')
    mode=env.get('FINDER_MODE','dummy')
    if mode not in ('dummy','offline','proxy'):raise ValueError('FINDER_MODE must be dummy, offline or proxy')
    host=env.get('FINDER_LISTEN_HOST','127.0.0.1').strip();address=ipaddress.ip_address(host)
    lan=not address.is_loopback
    network=env.get('FINDER_LAN_NETWORK','192.168.0.0/16')
    validate_listener(host,lan,network)  # Specific192.168 interface, password and peer policy; never wildcard.
    result=['-m','finderlab','web','--listen-host',host,'--listen-port',str(integer(env,'FINDER_WEB_PORT',8000,1,65535)),
            '--data-dir','/app/web-data','--storage-limit-mib',str(integer(env,'FINDER_STORAGE_MIB',256,128,2048))]
    if lan:result+=['--lan','--lan-network',network]
    if not boolean(env,'FINDER_AUTO_ARCHIVE',True):result+=['--no-auto-archive']
    slicing=boolean(env,'FINDER_ENABLE_SLICING')
    if slicing:
        if not orca.is_file() or not os.access(orca,os.X_OK):raise ValueError('Slicing runtime absent; add compose.slicing.yml and rebuild')
        for kind in ('machine','process','filament'):
            path=profile_dir/(kind+'.json')
            if not path.is_file() or not 0<path.stat().st_size<=1024*1024:
                raise ValueError('Missing/bounded trusted '+str(path)+'; copy your separately reviewed self-contained profiles (not supplied by Git)')
            result+=['--'+kind,str(path)]
        result+=['--orca',str(orca),'--check-priming']
    upload=boolean(env,'FINDER_ENABLE_UPLOAD');jobs=boolean(env,'FINDER_ENABLE_JOB_CONTROLS')
    generated=boolean(env,'FINDER_ALLOW_SLICED_UPLOAD');monitor=boolean(env,'FINDER_ENABLE_MONITOR');auto=boolean(env,'FINDER_AUTO_MONITOR')
    if mode!='proxy' and any((upload,jobs,generated,monitor,auto)):
        raise ValueError('Printer capability flags require FINDER_MODE=proxy; dummy owns virtual permissions and offline stays disconnected')
    if mode=='dummy':result+=['--dummy']
    if mode=='proxy':
        if jobs and not upload:raise ValueError('Combined workflow job controls require FINDER_ENABLE_UPLOAD=true')
        if generated and (not slicing or not upload):raise ValueError('Generated output saving requires configured slicing and enabled upload')
        if auto and not monitor:raise ValueError('Automatic status requires FINDER_ENABLE_MONITOR=true')
        result+=['--target-host','127.0.0.1','--target-port',str(integer(env,'FINDER_PROXY_PORT',9000,1,65535))]
        for enabled,flag in ((upload,'--enable-upload'),(jobs,'--enable-job-controls'),(generated,'--allow-sliced-upload'),(monitor,'--enable-monitor'),(auto,'--auto-monitor')):
            if enabled:result.append(flag)
    return result


def main():
    try:
        if len(sys.argv)>1:raise ValueError('Use FINDER_* environment settings, or override the entrypoint explicitly for raw CLI arguments')
        args=command(os.environ)
    except (ValueError,OSError) as exc:sys.exit('Container configuration error: '+str(exc))
    print('Finderlab container: explicit configuration, no discovery; LAN login password is printed by the web process. Proxy is not a safety filter.',flush=True)
    os.chdir(Path(__file__).resolve().parents[1])
    os.execv(sys.executable,[sys.executable,*args])


if __name__=='__main__':main()

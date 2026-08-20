"""LZSS compression.

compress(data) returns an LZSS stream that lzs.decompress() turns back into data.

Contract: output is a VALID stream, not a byte-exact reproduction of Heart Beat's.
Their matcher finds longer matches than this one at some positions, so recompressed
blocks differ from the originals while decompressing correctly. Measured on a
stratified sample: every block round-tripped, total output was slightly larger.

max_chain bounds the hash chain walk and trades speed for match quality.

Format details are in FORMAT.md section 2.
"""
N=4096; F=18; THRESHOLD=2

def compress(data, max_chain=48):
    ring=bytearray(N); r=N-F
    head={}; prev=[-1]*N
    written=0
    out=bytearray(); flagpos=None; flagbit=0; flags=0
    def verify(off,i,maxlen):
        cnt=0; rr=r; local={}
        for k in range(maxlen):
            p=(off+k)&(N-1)
            c=local[p] if p in local else ring[p]
            if data[i+k]!=c: break
            local[rr]=c; rr=(rr+1)&(N-1); cnt+=1
        return cnt
    i=0; n=len(data)
    while i<n:
        if flagbit==0:
            flagpos=len(out); out.append(0); flags=0; flagbit=1
        maxlen=min(F,n-i)
        best=0; bestoff=0
        if maxlen>=THRESHOLD+1:
            cands=[]
            key=bytes(data[i:i+3])
            p=head.get(key,-1); c=0
            while p!=-1 and c<max_chain:
                cands.append(p); p=prev[p]; c+=1
            cands.append((r-1)&(N-1))   # run of the previous byte
            cands.append((r+1)&(N-1))   # unwritten zero region
            for off in cands:
                if best>=maxlen: break
                l=verify(off,i,maxlen)
                if l>best: best=l; bestoff=off
        if best>THRESHOLD:
            out.append(bestoff & 0xFF)
            out.append(((bestoff>>4)&0xF0) | (best-THRESHOLD-1))
            ln=best
        else:
            flags |= (1<<(flagbit-1))
            out.append(data[i]); ln=1
        for k in range(ln):
            c=data[i+k]
            ring[r]=c
            written+=1
            if written>=3:
                sp=(r-2)&(N-1)
                key=bytes((ring[sp],ring[(sp+1)&(N-1)],ring[(sp+2)&(N-1)]))
                prev[sp]=head.get(key,-1); head[key]=sp
            r=(r+1)&(N-1)
        i+=ln
        flagbit+=1
        if flagbit==9:
            out[flagpos]=flags; flagbit=0
    if flagbit: out[flagpos]=flags
    return bytes(out)

#!/usr/bin/env python3
"""Seal independently verified ROM-free host-mock and real NeXium evidence.

The two domains have DIFFERENT provenance. Guest evidence is a real NRO
execution inside the emulator, not physical speaker or original arcade
audio. Host mock timing is synthetic, not NeXium timing.
"""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from tools import nexium_audio_release_corpus as corpus
    from tools import verify_nexium_audio_controlled_oracle as host
    from tools import verify_nexium_audio_paired_artifacts as guest
else:
    import nexium_audio_release_corpus as corpus
    import verify_nexium_audio_controlled_oracle as host
    import verify_nexium_audio_paired_artifacts as guest

SCHEMA='dino-audio-two-domain-provenance-manifest-v1'
FILES=(
    'host-plan','host-result','host-oracle',
    'corpus-plan','corpus-result','corpus-attestation',
    'baseline-report','baseline-binding','baseline-nro',
    'experimental-report','experimental-binding','experimental-nro',
    'guest-comparison',
)
HOST_KEYS=FILES[:6]
GUEST_KEYS=FILES[6:]


def read_source(path, limit):
    p=Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError('missing or symlinked evidence source')
    size=p.stat().st_size
    if not 64<=size<=limit:
        raise ValueError('invalid bounded evidence source size')
    raw=p.read_bytes()
    if len(raw)!=size:
        raise ValueError('evidence source changed during read')
    return raw


def strict_json(raw):
    try:
        return json.loads(raw.decode('ascii'),object_pairs_hook=host.no_duplicate_keys)
    except (UnicodeError,json.JSONDecodeError) as err:
        raise ValueError('malformed evidence JSON') from err


def verify(files):
    if type(files) is not dict or set(files)!=set(FILES):
        raise ValueError('incomplete two-domain evidence source set')
    raw={}
    for key,path in files.items():
        raw[key]=read_source(path,1048576 if key.endswith('-nro') else 262144)
    actual_host=strict_json(raw['host-oracle'])
    expected_host=host.verify(files['host-plan'],files['host-result'])
    if not host.exactly_equal(actual_host,expected_host):
        raise ValueError('independent host oracle attestation mismatch')
    actual_corpus=strict_json(raw['corpus-attestation'])
    expected_corpus=corpus.attest(files['corpus-plan'],files['corpus-result'])
    if not host.exactly_equal(actual_corpus,expected_corpus):
        raise ValueError('six-scenario host corpus attestation mismatch')
    actual_guest=strict_json(raw['guest-comparison'])
    expected_guest=guest.compare(
        files['baseline-report'],files['baseline-binding'],
        files['experimental-report'],files['experimental-binding'],
        files['baseline-nro'],files['experimental-nro'])
    if not host.exactly_equal(actual_guest,expected_guest):
        raise ValueError('real guest bound A/B comparison mismatch')
    if (actual_host['status']!='CONTROLLED_NATIVE_C_LEDGER_MATCHES_INDEPENDENT_ORACLE' or
            actual_corpus['status']!='SIX_NATIVE_C_RELEASE_SCENARIOS_MATCH_ORACLE' or
            actual_guest['status']!='UNCONTROLLED_BOUND_GUEST_AUDIO_COMPARISON_DESCRIPTIVE_ONLY'):
        raise ValueError('wrong evidence domain status')
    if (actual_host['physical_switch_audio_verified'] is not False or
            actual_corpus['physical_switch_audio_verified'] is not False or
            actual_guest['physical_switch_audio_verified'] is not False or
            actual_guest['host_conditions_matched_verified'] is not False or
            actual_guest['causal_audio_improvement_verified'] is not False):
        raise ValueError('unverified hardware or causal audio claim')
    if actual_corpus['verified_ticks_per_mode']!=900 or len(actual_corpus['verified_scenarios'])!=6:
        raise ValueError('wrong controlled C corpus scope')
    hashes={key:hashlib.sha256(value).hexdigest() for key,value in raw.items()}
    return {
        'schema':SCHEMA,
        'status':'HOST_AND_GUEST_EVIDENCE_INDEPENDENTLY_BOUND',
        'scope':'ROM_FREE_SHA256_BOUND_TWO_DOMAIN_SUMMARY',
        'host_native_c_domain':{
            'file_sha256':{key:hashes[key] for key in HOST_KEYS},
            'controlled_synthetic_scenarios':list(actual_corpus['verified_scenarios']),
            'synthetic_ticks_per_mode':actual_corpus['verified_ticks_per_mode'],
            'native_mock_oracle_validated':True,
            'emulator_frame_pacing_verified':False,
        },
        'real_nexium_guest_domain':{
            'file_sha256':{key:hashes[key] for key in GUEST_KEYS},
            'guest_mode_binding_validated':True,
            'baseline_skipped':actual_guest['descriptive_comparison']['baseline']['audio_blocks_skipped'],
            'experimental_skipped':actual_guest['descriptive_comparison']['experimental']['audio_blocks_skipped'],
            'matched_guest_host_conditions_verified':False,
        },
        'synthetic_host_and_real_guest_evidence_interchangeable':False,
        'physical_switch_audio_verified':False,
        'original_arcade_audio_verified':False,
        'causal_audio_improvement_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in FILES:
        p.add_argument('--'+key,required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    args=p.parse_args(argv)
    try:
        result=verify({key:getattr(args,key.replace('-','_')) for key in FILES})
        with args.out.open('x',encoding='ascii') as f:
            f.write(json.dumps(result,sort_keys=True)+'\n')
        code=0
    except (ValueError,OSError,TypeError,KeyError,OverflowError) as err:
        result={
            'schema':SCHEMA,
            'status':'INCONCLUSIVE_TWO_DOMAIN_PROVENANCE',
            'reason':type(err).__name__,
            'physical_switch_audio_verified':False,
            'causal_audio_improvement_verified':False,
        }
        code=1
    print(json.dumps(result,sort_keys=True))
    return code


if __name__=='__main__':
    raise SystemExit(main())

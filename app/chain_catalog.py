"""The Blockchain section: three chain types, one page each, plus a comparison."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ChainSpec:
    slug: str
    title: str
    subtitle: str
    blurb: str
    template: str
    consensus: str
    who_writes: str
    trust: str
    icon: str = '⛓'

    @property
    def url(self) -> str:
        return f'/blockchain/{self.slug}'


CHAINS: list[ChainSpec] = [
    ChainSpec(
        slug='ledger', title='Public ledger', subtitle='Proof of work · anyone can write',
        blurb='An open, append-only record. Anyone submits entries, anyone mines. Tamper with a stored block and watch '
              'verification fail from that point on — then see what it costs an attacker to hide it.',
        template='chain/ledger.html', consensus='Proof of work (leading-zero hash puzzle)',
        who_writes='Anyone who mines a block', trust='Nobody in particular; the cost of redoing the work', icon='⛏',
    ),
    ChainSpec(
        slug='permissioned', title='Permissioned ledger', subtitle='Proof of authority · known validators',
        blurb='A consortium budget ledger for government agencies. Named validators sign blocks with Ed25519 keys; '
              'every transaction is signed by its sender and validated against balances derived from the chain itself.',
        template='chain/permissioned.html', consensus='Proof of authority (validator signatures)',
        who_writes='Approved validators only', trust='The identified validators and their keys', icon='🏛',
    ),
    ChainSpec(
        slug='coin', title='Cryptocurrency', subtitle='UTXO model · mining rewards · halving',
        blurb='Wallets with real keypairs, coins as unspent outputs, signed spends with change and fees, coinbase rewards '
              'that halve, difficulty that adjusts, and a double-spend attempt that fails.',
        template='chain/coin.html', consensus='Proof of work with difficulty adjustment',
        who_writes='Anyone who mines; spending needs the owner\'s key', trust='The keys and the work', icon='🪙',
    ),
]

CHAINS_BY_SLUG = {c.slug: c for c in CHAINS}

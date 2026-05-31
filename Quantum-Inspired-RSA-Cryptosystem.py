"""
╔══════════════════════════════════════════════════════════════════╗
║          ⚛  Quantum-Inspired RSA Simulator                      ║
║          FURG — Matemática Aplicada                              ║
║                                                                  ║
║  Geração de chaves RSA com entropia quântica via Qiskit Aer.     ║
║  Um circuito Hadamard colapsa qubits em superposição para        ║
║  produzir bits não-determinísticos — substituindo o PRNG         ║
║  clássico (random.randrange) na geração de p, q e e.             ║
║                                                                  ║
║  NOTA: usa AerSimulator (local). Para entropia quântica real,    ║
║  substituir por IBM Quantum hardware via QiskitRuntimeService.   ║
╚══════════════════════════════════════════════════════════════════╝

USO RÁPIDO:
    python quantum_rsa.py
    python quantum_rsa.py --message "FURG" --bits 512
    python quantum_rsa.py --demo-entropy --samples 300
    python quantum_rsa.py --demo-benchmark
"""

# ─── stdlib ───────────────────────────────────────────────────────────────────
import argparse
import json
import math
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

# ─── qiskit ───────────────────────────────────────────────────────────────────
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator


# ══════════════════════════════════════════════════════════════════════════════
#  1. QUANTUM RNG
#  Um gate Hadamard coloca cada qubit em |+⟩ = (|0⟩+|1⟩)/√2.
#  A medição colapsa o estado — resultado não computável a partir
#  de nenhum estado anterior (não-determinismo verdadeiro no hardware,
#  simulado classicamente no Aer).
# ══════════════════════════════════════════════════════════════════════════════

def quantum_random_int(min_value: int, max_value: int) -> int:
    """
    Retorna inteiro quântico-aleatório em [min_value, max_value] (inclusive).

    Estratégia: ceil(log2(range+1)) qubits, H em todos, 1 shot.
    O bitstring resultante é mapeado ao intervalo alvo via módulo
    (bias desprezível quando range << 2^num_bits).
    """
    if min_value > max_value:
        raise ValueError(f"min_value ({min_value}) deve ser ≤ max_value ({max_value})")
    if min_value == max_value:
        return min_value

    interval  = max_value - min_value
    num_bits  = max(1, math.ceil(math.log2(interval + 1)))

    qc = QuantumCircuit(num_bits, num_bits)
    for i in range(num_bits):
        qc.h(i)                                     # superposição
    qc.measure(range(num_bits), range(num_bits))

    job      = AerSimulator().run(qc, shots=1, memory=True)
    bitstring = job.result().get_memory()[0]
    return min_value + (int(bitstring, 2) % (interval + 1))


def quantum_random_large_int(bit_length: int) -> int:
    """
    Gera inteiro quântico de exatamente `bit_length` bits.
    MSB forçado em 1 para garantir o comprimento correto.
    Usado como semente de candidatos primos RSA.
    """
    if bit_length < 1:
        raise ValueError("bit_length deve ser ≥ 1")

    qc = QuantumCircuit(bit_length, bit_length)
    for i in range(bit_length):
        qc.h(i)
    qc.measure(range(bit_length), range(bit_length))

    job      = AerSimulator().run(qc, shots=1, memory=True)
    bits     = job.result().get_memory()[0]
    bits     = "1" + bits[1:]          # força MSB=1
    return int(bits, 2)


# ══════════════════════════════════════════════════════════════════════════════
#  2. PRIMALIDADE — Miller-Rabin k=20
#  k=20 rodadas → probabilidade de falso-positivo < 4^(-20) ≈ 10^(-12)
# ══════════════════════════════════════════════════════════════════════════════

_SMALL_PRIMES = [
    2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,
    53,59,61,67,71,73,79,83,89,97,101,103,107,109,113,
]

def miller_rabin(n: int, k: int = 20) -> bool:
    """Teste de primalidade probabilístico. Retorna True se provavelmente primo."""
    if n < 2:   return False
    if n in (2, 3): return True
    if n % 2 == 0:  return False

    # pré-filtro rápido com pequenos primos
    for sp in _SMALL_PRIMES:
        if n == sp:    return True
        if n % sp == 0: return False

    # escreve n-1 como 2^r * d
    r, d = 0, n - 1
    while d % 2 == 0:
        r += 1
        d //= 2

    for _ in range(k):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False        # definitivamente composto
    return True                 # provavelmente primo


def next_prime(n: int) -> int:
    """Menor primo ≥ n."""
    if n < 2: return 2
    cand = n if n % 2 != 0 else n + 1
    while not miller_rabin(cand):
        cand += 2
    return cand


# ══════════════════════════════════════════════════════════════════════════════
#  3. MATEMÁTICA RSA
# ══════════════════════════════════════════════════════════════════════════════

def gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def extended_gcd(a: int, b: int):
    """Retorna (mdc, x, y) tal que a*x + b*y = mdc."""
    if a == 0:
        return b, 0, 1
    g, x, y = extended_gcd(b % a, a)
    return g, y - (b // a) * x, x


def mod_inverse(a: int, m: int) -> int:
    """Inverso modular de a mod m via Algoritmo Estendido de Euclides."""
    g, x, _ = extended_gcd(a % m, m)
    if g != 1:
        raise ValueError(f"Inverso modular não existe para a={a}, m={m}")
    return x % m


# ══════════════════════════════════════════════════════════════════════════════
#  4. GERAÇÃO DE CHAVES RSA
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RSAKeyPair:
    e:   int    # expoente público
    d:   int    # expoente privado
    n:   int    # módulo
    p:   int    # fator primo (secreto)
    q:   int    # fator primo (secreto)
    phi: int    # totiente de Euler (secreto)
    bit_length: int


def _quantum_prime(bit_length: int) -> int:
    """Gera primo de ~bit_length bits com semente quântica."""
    candidate = quantum_random_large_int(bit_length)
    if candidate % 2 == 0:
        candidate += 1
    return next_prime(candidate)


def generate_keypair(bit_length: int = 512, verbose: bool = True) -> RSAKeyPair:
    """
    Gera par de chaves RSA com aleatoriedade quântica.

    bit_length : tamanho em bits de cada primo p e q.
                 O módulo n terá ~2*bit_length bits.
                 Mínimo seguro: 1024 (demo rápido: 128–256).
    """
    if verbose:
        print(f"\n[RSA] Gerando primos de {bit_length} bits via quantum RNG...")

    p = _quantum_prime(bit_length)
    if verbose:
        print(f"[RSA]   p = {str(p)[:20]}...  ({p.bit_length()} bits)")

    q = _quantum_prime(bit_length)
    attempts = 1
    while q == p:
        q = _quantum_prime(bit_length)
        attempts += 1
    if verbose:
        print(f"[RSA]   q = {str(q)[:20]}...  ({q.bit_length()} bits)  [{attempts} tentativa(s)]")

    n   = p * q
    phi = (p - 1) * (q - 1)

    if verbose:
        print("[RSA] Amostrando expoente público e via quantum RNG...")
    e, tries = 0, 0
    while e == 0:
        tries += 1
        cand = quantum_random_int(2, phi - 1)
        if gcd(cand, phi) == 1:
            e = cand
    if verbose:
        print(f"[RSA]   e encontrado em {tries} amostra(s) quântica(s)")

    d = mod_inverse(e, phi)

    return RSAKeyPair(e=e, d=d, n=n, p=p, q=q, phi=phi, bit_length=bit_length)


# ══════════════════════════════════════════════════════════════════════════════
#  5. CIFRAGEM / DECIFRAGEM
#  ATENÇÃO: RSA textbook (sem padding) — apenas para fins didáticos.
#  Produção real exige OAEP ou PKCS#1 v1.5.
# ══════════════════════════════════════════════════════════════════════════════

def encrypt(message: str, e: int, n: int) -> List[int]:
    """Cifra string UTF-8 byte a byte com RSA."""
    return [pow(b, e, n) for b in message.encode("utf-8")]


def decrypt(ciphertext: List[int], d: int, n: int) -> str:
    """Decifra lista de inteiros RSA de volta para string UTF-8."""
    return bytes(pow(c, d, n) for c in ciphertext).decode("utf-8")


# ══════════════════════════════════════════════════════════════════════════════
#  6. LOGGER DE EXPERIMENTOS (JSONL)
# ══════════════════════════════════════════════════════════════════════════════

_LOG_FILE = "quantum_rsa_runs.jsonl"

def log_run(experiment: str, params: dict, results: dict, elapsed_s: float):
    """Append de um registro JSON no arquivo de log."""
    entry = {
        "experiment": experiment,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "elapsed_s":  round(elapsed_s, 4),
        "params":     params,
        "results":    results,
    }
    with open(_LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[log] → {_LOG_FILE}")


# ══════════════════════════════════════════════════════════════════════════════
#  7. EXPERIMENTO: ANÁLISE DE ENTROPIA
#  Compara distribuição do Quantum RNG vs PRNG clássico.
#  Métricas: entropia de Shannon + estatística chi-quadrado.
# ══════════════════════════════════════════════════════════════════════════════

def shannon_entropy(samples: list, n_bins: int) -> float:
    counts = [0] * n_bins
    for s in samples:
        counts[s % n_bins] += 1
    total   = len(samples)
    entropy = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            entropy -= p * math.log2(p)
    return entropy


def chi_squared(samples: list, n_bins: int) -> float:
    counts   = [0] * n_bins
    for s in samples:
        counts[s % n_bins] += 1
    expected = len(samples) / n_bins
    return sum((c - expected) ** 2 / expected for c in counts)


def ascii_histogram(label: str, samples: list, n_bins: int, width: int = 36):
    counts = [0] * n_bins
    for s in samples:
        counts[s % n_bins] += 1
    max_c = max(counts) or 1
    print(f"\n  {label}  ({n_bins} bins, {len(samples)} amostras)")
    for i, c in enumerate(counts):
        bar = "█" * int(c / max_c * width)
        print(f"  {i:3d} | {bar:<{width}} {c}")


def demo_entropy(n_samples: int = 200, max_val: int = 15):
    n_bins = max_val + 1
    print(f"\n{'═'*56}")
    print(f"  ANÁLISE DE ENTROPIA  —  {n_samples} amostras  (0–{max_val})")
    print(f"{'═'*56}")

    print(f"\n[Quantum RNG] coletando {n_samples} amostras...")
    t0 = time.perf_counter()
    q_samples = [quantum_random_int(0, max_val) for _ in range(n_samples)]
    q_time    = time.perf_counter() - t0

    print(f"[PRNG clássico] coletando {n_samples} amostras...")
    t0 = time.perf_counter()
    c_samples = [random.randint(0, max_val) for _ in range(n_samples)]
    c_time    = time.perf_counter() - t0

    max_entropy = math.log2(n_bins)

    for label, samples, elapsed in [
        ("Quantum RNG (Qiskit Aer)", q_samples, q_time),
        ("PRNG clássico (random)",   c_samples, c_time),
    ]:
        ent  = shannon_entropy(samples, n_bins)
        chi2 = chi_squared(samples, n_bins)
        print(f"\n  ── {label} ──")
        print(f"  Entropia de Shannon : {ent:.4f} bits  (máx: {max_entropy:.4f})")
        print(f"  Ratio               : {ent/max_entropy:.4%}  (1.0 = perfeito)")
        print(f"  Chi-quadrado        : {chi2:.2f}  (menor = mais uniforme)")
        print(f"  Tempo total         : {elapsed:.3f}s")
        ascii_histogram(label, samples, n_bins)

    log_run("entropy_analysis",
            {"n_samples": n_samples, "max_val": max_val},
            {"q_entropy": round(shannon_entropy(q_samples, n_bins), 6),
             "c_entropy": round(shannon_entropy(c_samples, n_bins), 6)},
            q_time + c_time)


# ══════════════════════════════════════════════════════════════════════════════
#  8. EXPERIMENTO: BENCHMARK QUANTUM vs CLÁSSICO
# ══════════════════════════════════════════════════════════════════════════════

def demo_benchmark(n_runs: int = 10, max_val: int = 9999):
    print(f"\n{'═'*56}")
    print(f"  BENCHMARK  —  {n_runs} amostras  (0–{max_val})")
    print(f"{'═'*56}")

    print(f"\n[Quantum RNG] {n_runs} chamadas...")
    t0 = time.perf_counter()
    for _ in range(n_runs):
        quantum_random_int(0, max_val)
    q_elapsed = time.perf_counter() - t0
    q_avg     = q_elapsed / n_runs

    print(f"[PRNG clássico] {n_runs} chamadas...")
    t0 = time.perf_counter()
    for _ in range(n_runs):
        random.randint(0, max_val)
    c_elapsed = time.perf_counter() - t0
    c_avg     = c_elapsed / n_runs

    speedup = q_avg / c_avg
    print(f"\n  Quantum  : {q_avg*1000:.2f} ms/chamada  (total {q_elapsed:.3f}s)")
    print(f"  Clássico : {c_avg*1000:.6f} ms/chamada  (total {c_elapsed:.6f}s)")
    print(f"  Overhead : clássico é {speedup:.0f}x mais rápido por chamada")
    print(f"  (esperado — overhead do circuito Aer vs PRNG in-process)")

    log_run("benchmark",
            {"n_runs": n_runs, "max_val": max_val},
            {"quantum_avg_ms": round(q_avg*1000, 4),
             "classical_avg_ms": round(c_avg*1000, 8),
             "speedup_classical": round(speedup, 1)},
            q_elapsed + c_elapsed)


# ══════════════════════════════════════════════════════════════════════════════
#  9. DEMO PRINCIPAL RSA
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
 ██████  ██████  ███████  █████
██    ██ ██   ██ ██      ██   ██
██    ██ ██████  ███████ ███████
██ ▄▄ ██ ██   ██      ██ ██   ██
 ██████  ██   ██ ███████ ██   ██
    ▀▀
  Quantum-Inspired RSA Simulator  |  FURG
"""

def demo_rsa(message: str, bit_length: int, do_log: bool = True):
    print(BANNER)
    print(f"  Mensagem   : {message!r}")
    print(f"  Bits primo : {bit_length}")

    # ── Geração de chaves ─────────────────────────────────────────────────────
    t0  = time.perf_counter()
    kp  = generate_keypair(bit_length=bit_length, verbose=True)
    t_keygen = time.perf_counter() - t0

    print(f"\n{'─'*54}")
    print(f"  Chaves RSA geradas em {t_keygen:.3f}s")
    print(f"  n   : {str(kp.n)[:40]}...  ({kp.n.bit_length()} bits)")
    print(f"  e   : {kp.e}")
    print(f"  d   : {str(kp.d)[:40]}...")
    print(f"  φ(n): {str(kp.phi)[:40]}...")

    # ── Cifragem ──────────────────────────────────────────────────────────────
    print(f"\n{'─'*54}")
    t1 = time.perf_counter()
    cipher = encrypt(message, kp.e, kp.n)
    t_enc  = time.perf_counter() - t1

    raw_bytes = list(message.encode("utf-8"))
    print(f"  Bytes originais    : {raw_bytes}")
    print(f"  Cifrado (primeiros 5): {cipher[:5]}")
    print(f"  Total de valores   : {len(cipher)}")
    print(f"  Tempo cifragem     : {t_enc*1000:.2f}ms")

    # ── Decifragem ────────────────────────────────────────────────────────────
    print(f"\n{'─'*54}")
    t2 = time.perf_counter()
    recovered = decrypt(cipher, kp.d, kp.n)
    t_dec     = time.perf_counter() - t2

    print(f"  Decifrado          : {recovered!r}")
    print(f"  Verificação        : {'✓ OK' if recovered == message else '✗ FALHOU'}")
    print(f"  Tempo decifragem   : {t_dec*1000:.2f}ms")
    print(f"{'─'*54}")

    if do_log:
        log_run("rsa_demo",
                {"bit_length": bit_length, "msg_len": len(message)},
                {"n_bits":      kp.n.bit_length(),
                 "keygen_s":    round(t_keygen, 4),
                 "encrypt_ms":  round(t_enc*1000, 4),
                 "decrypt_ms":  round(t_dec*1000, 4),
                 "success":     recovered == message},
                t_keygen + t_enc + t_dec)

    if recovered == message:
        print("\n  ✓  RSA cifrar→decifrar verificado com sucesso.")
    else:
        print("\n  ✗  ERRO: mensagem decifrada não bate com a original!")


# ══════════════════════════════════════════════════════════════════════════════
#  10. CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Quantum-Inspired RSA Simulator — FURG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
exemplos:
  python quantum_rsa.py
  python quantum_rsa.py --message "FURG" --bits 256 --log
  python quantum_rsa.py --demo-entropy --samples 300
  python quantum_rsa.py --demo-benchmark --runs 20
        """
    )
    parser.add_argument("--message",        type=str,  default="Matematica aplicada em FURG")
    parser.add_argument("--bits",           type=int,  default=128,
                        help="bits de cada primo p e q (padrão: 128; use 512+ para segurança)")
    parser.add_argument("--log",            action="store_true", help="salva run em quantum_rsa_runs.jsonl")
    parser.add_argument("--demo-entropy",   action="store_true", help="análise de entropia quantum vs clássico")
    parser.add_argument("--demo-benchmark", action="store_true", help="benchmark de velocidade")
    parser.add_argument("--samples",        type=int,  default=200, help="amostras para --demo-entropy")
    parser.add_argument("--runs",           type=int,  default=10,  help="iterações para --demo-benchmark")

    args = parser.parse_args()

    if args.demo_entropy:
        demo_entropy(n_samples=args.samples)
    elif args.demo_benchmark:
        demo_benchmark(n_runs=args.runs)
    else:
        demo_rsa(message=args.message, bit_length=args.bits, do_log=args.log)


if __name__ == "__main__":
    main()
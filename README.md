# ⚛️ Quantum-Inspired RSA Simulator

Implementação do algoritmo RSA onde a geração de entropia das chaves utiliza **medições quânticas reais** via Qiskit/Aer — substituindo o gerador pseudoaleatório clássico (`random.randrange`) por colapso de qubits em superposição.

Desenvolvido como projeto de **Matemática Aplicada — FURG**.

---

## O que esse projeto faz?

O RSA clássico depende de `random.randrange()` para gerar os números primos `p` e `q`. Esse gerador é *pseudoaleatório*: determinístico, baseado em semente.

Aqui, substituímos isso por um **circuito quântico**: aplicamos o gate Hadamard em cada qubit, colocando-o em superposição |+⟩ = (|0⟩+|1⟩)/√2. A medição colapsa o estado de forma não-determinística — o resultado não pode ser previsto nem reproduzido a partir de nenhum estado anterior.

O resultado: geração de chaves RSA enraizada em **aleatoriedade quântica**, não em pseudo-aleatoriedade.

---

## Como rodar

```bash
pip install qiskit qiskit-aer
python quantum_rsa.py
```

```bash
# RSA com primos de 512 bits + log do experimento
python quantum_rsa.py --message "FURG" --bits 512 --log

# Análise de entropia: Quantum RNG vs random.randint
python quantum_rsa.py --demo-entropy --samples 300

# Benchmark de velocidade: overhead do circuito vs PRNG
python quantum_rsa.py --demo-benchmark --runs 20
```

---

## O que foi melhorado em relação ao RSA clássico

| Problema | Solução |
|---|---|
| Primos de ~13 bits (200–9999) | Tamanho configurável: 128, 512, 1024, 2048+ bits |
| Miller-Rabin com k=10 | k=20 rodadas + sieve de 30 pequenos primos como pré-filtro |
| Sem análise estatística | Shannon entropy + chi-quadrado comparando Quantum vs PRNG |
| Sem benchmark | Medição real do overhead do circuito Aer vs `random.randint` |
| Sem logging | Salva cada experimento em `quantum_rsa_runs.jsonl` com timestamp e métricas |

---

## Nota acadêmica

Este projeto usa o **AerSimulator** (simulação local), não hardware quântico real.
Para entropia quântica verdadeira em hardware: substituir `AerSimulator` por um backend IBM Quantum via `QiskitRuntimeService`.
A simulação demonstra a arquitetura; a qualidade da entropia depende do backend utilizado.

---

## Stack

- Python 3.10+
- Qiskit · Qiskit-Aer
- Nenhuma dependência além dessas

---

*FURG — Matemática Aplicada*

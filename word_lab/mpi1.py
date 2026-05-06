import os
import time
from collections import Counter
from mpi4py import MPI

def cargar_consulta(consulta_path, case_sensitive=False):
    with open(consulta_path, "r", encoding="utf-8") as f:
        palabras = [line.strip() for line in f if line.strip()]
    if not case_sensitive:
        palabras = [w.lower() for w in palabras]
    return set(palabras)

def contar_en_archivos(archivos, palabras_objetivo, case_sensitive=False):
    freq = Counter()
    for ruta in archivos:
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                palabras = linea.split()
                if not case_sensitive:
                    palabras = [w.lower() for w in palabras]
                for w in palabras:
                    if w in palabras_objetivo:
                        freq[w] += 1
    return freq

def main():
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    case_sensitive = False
    top_n = 10

    t_total_ini = time.perf_counter()
    # --- rank 0: preparar datos ---
    if rank == 0:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dataset_dir = os.path.join(script_dir, "dataset")

        # 1. Leer consulta
        consulta_path = os.path.join(dataset_dir, "consulta.txt")
        palabras_objetivo = cargar_consulta(consulta_path, case_sensitive)

        # 2. Obtener lista de archivos del corpus
        todos_archivos = sorted([
            os.path.join(dataset_dir, f)
            for f in os.listdir(dataset_dir)
            if f.startswith("file_") and f.endswith(".txt")
        ])

        # 3. Distribuir estáticamente (round-robin)
        distribucion = [[] for _ in range(size)]
        for i, archivo in enumerate(todos_archivos):
            distribucion[i % size].append(archivo)
    else:
        palabras_objetivo = None
        distribucion = None

    # --- broadcast palabras objetivo ---
    palabras_objetivo = comm.bcast(palabras_objetivo, root=0)

    # --- scatter de archivos asignados a cada proceso ---
    mis_archivos = comm.scatter(distribucion, root=0)

    # --- cada proceso cuenta localmente ---
    t_local_ini = time.perf_counter()
    freq_local = contar_en_archivos(mis_archivos, palabras_objetivo, case_sensitive)
    t_local_fin = time.perf_counter()
    t_local = t_local_fin - t_local_ini

    print(f"[Rank {rank}] Archivos asignados: {len(mis_archivos)} | "
          f"Tiempo local: {t_local:.6f}s", flush=True)

    # --- gather resultados parciales en rank 0 ---
    todos_freq = comm.gather(freq_local, root=0)
    t_prom = comm.reduce(t_local, op=MPI.SUM, root=0)

    # --- rank 0: combinar y mostrar top 10 ---
    if rank == 0:
        t_total_fin = time.perf_counter()
        t_total = t_total_fin - t_total_ini

        freq_global = Counter()
        for freq in todos_freq:
            freq_global.update(freq)

        top_words = freq_global.most_common(top_n)
        print(f"\nTop {top_n} palabras:")
        for palabra, cuenta in top_words:
            print(f"  {palabra}: {cuenta}")

        print(f"\nTiempo total: {t_total:.6f}s")
        print(f"Tiempo promedio por proceso: {t_prom/size:.6f}s")

main()
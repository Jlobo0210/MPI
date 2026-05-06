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

def distribuir_por_carga(archivos, num_procesos):
    """
    Distribuye archivos asignando cada archivo al proceso
    con menor carga acumulada (greedy por tamaño de archivo).
    Esto minimiza el desbalance cuando los archivos varían en tamaño.
    """
    # Ordenar de mayor a menor tamaño
    archivos_con_tam = sorted(
        [(f, os.path.getsize(f)) for f in archivos],
        key=lambda x: x[1],
        reverse=True
    )

    carga = [0] * num_procesos          # bytes acumulados por proceso
    asignacion = [[] for _ in range(num_procesos)]

    for archivo, tam in archivos_con_tam:
        proceso_min = carga.index(min(carga))   # proceso con menos carga
        asignacion[proceso_min].append(archivo)
        carga[proceso_min] += tam

    return asignacion

def main():
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    case_sensitive = False
    top_n = 10
    t_total_ini = time.perf_counter()
    
    if rank == 0:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dataset_dir = os.path.join(script_dir, "dataset")

        consulta_path = os.path.join(dataset_dir, "consulta.txt")
        palabras_objetivo = cargar_consulta(consulta_path, case_sensitive)

        todos_archivos = sorted([
            os.path.join(dataset_dir, f)
            for f in os.listdir(dataset_dir)
            if f.startswith("file_") and f.endswith(".txt")
        ])

        # Distribución inteligente por tamaño de archivo
        distribucion = distribuir_por_carga(todos_archivos, size)
    else:
        palabras_objetivo = None
        distribucion = None

    # Broadcast de palabras objetivo
    palabras_objetivo = comm.bcast(palabras_objetivo, root=0)

    # Scatter de archivos
    mis_archivos = comm.scatter(distribucion, root=0)

    # Conteo local
    t_local_ini = time.perf_counter()
    freq_local = contar_en_archivos(mis_archivos, palabras_objetivo, case_sensitive)
    t_local_fin = time.perf_counter()
    t_local = t_local_fin - t_local_ini

    # Calcular carga en bytes de este proceso
    carga_bytes = sum(os.path.getsize(f) for f in mis_archivos) if mis_archivos else 0

    print(f"[Rank {rank}] Archivos: {len(mis_archivos)} | "
          f"Carga: {carga_bytes/1024:.1f} KB | "
          f"Tiempo local: {t_local:.6f}s", flush=True)

    # Gather en rank 0
    todos_freq = comm.gather(freq_local, root=0)
    t_prom = comm.reduce(t_local, op=MPI.SUM, root=0)
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
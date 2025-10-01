import grpc
from concurrent import futures
import time
import itertools

import calculo_pb2
import calculo_pb2_grpc


def sum_squares_local(a: int, b: int) -> int:
    """Cálculo local de sumatoria de cuadrados entre a y b (inclusive)."""
    # implementación simple y robusta
    total = 0
    for i in range(a, b + 1):
        total += i * i
    return total


class CalculoService(calculo_pb2_grpc.CalculoServiceServicer):
    def __init__(self, workers):
        self.workers = workers
        # ciclo round-robin sobre índices (0..N-1)
        self.rr_counter = itertools.cycle(range(max(1, len(workers))))

    def enviar_a_worker(self, request, worker_addr):
        """
        Intenta enviar request a worker_addr.
        Retorna (response, worker_addr) o (None, worker_addr) si falla.
        """
        try:
            channel = grpc.insecure_channel(worker_addr)
            stub = calculo_pb2_grpc.OperacionServiceStub(channel)
            # llamar con timeout corto para no bloquear mucho
            response = stub.Calcular(request, timeout=5)
            return response, worker_addr
        except Exception as e:
            print(f"❌ Error conectando a worker {worker_addr}: {e}")
            return None, worker_addr

    def CalculoTotal(self, request, context):
        op = request.op
        print(f"\n[COORDINADOR] Nueva operación recibida: {op}")
        print(f"[COORDINADOR] Datos recibidos -> a={request.a}, b={request.b}, n={request.n}")

        num_workers = len(self.workers)

        # --- operaciones básicas (add, sub, mul, div) ---
        if op in ("add", "sub", "mul", "div"):
            # Intentar usar los workers primero
            any_worker_responded = False
            last_non_ok_response = None

            for _ in range(max(1, num_workers)):
                idx = next(self.rr_counter)
                worker_addr = self.workers[idx]
                print(f"[COORDINADOR] Intentando operación básica {op} en worker {worker_addr}")
                response, used_worker = self.enviar_a_worker(request, worker_addr)
                if response is None:
                    print(f"[COORDINADOR] ❌ Sin respuesta de worker {worker_addr}, probando siguiente")
                    continue
                any_worker_responded = True
                if response.ok:
                    print(f"[COORDINADOR] ✅ Worker {used_worker} devolvió resultado: {response.result}")
                    # Retornar la respuesta tal cual (cliente no conoce fallos)
                    return response
                else:
                    # Worker respondió pero con error (ej: división por cero)
                    print(f"[COORDINADOR] ⚠️ Worker {used_worker} devolvió error: {response.error}")
                    last_non_ok_response = response
                    # si es error por operación (ej división por cero) devolvemos ese error al cliente
                    return response

            # Si llegamos aquí, ningún worker respondió con ok ni con error procesable.
            if not any_worker_responded:
                # fallback local: el coordinador resuelve la operación por su cuenta
                print("[COORDINADOR] ⚠️ Ningún worker disponible para operación básica. Resolviendo localmente.")
                try:
                    a = float(request.a)
                    b = float(request.b)
                    if op == "add":
                        r = a + b
                    elif op == "sub":
                        r = a - b
                    elif op == "mul":
                        r = a * b
                    elif op == "div":
                        if b == 0:
                            print("[COORDINADOR] ❌ División por cero detectada localmente.")
                            return calculo_pb2.CalculoResponse(ok=False, error="División por cero")
                        r = a / b
                    print(f"[COORDINADOR] ✅ Resultado local: {r}")
                    return calculo_pb2.CalculoResponse(ok=True, result=float(r))
                except Exception as e:
                    print(f"[COORDINADOR] ❌ Error al calcular localmente: {e}")
                    return calculo_pb2.CalculoResponse(ok=False, error="error_internal")

            # Si algún worker respondió no-ok lo hemos devuelto arriba; si no, caemos en error genérico
            return calculo_pb2.CalculoResponse(ok=False, error="Ningún worker disponible")

        # --- sumatoria de cuadrados ---
        elif op == "sum_squares":
            n = int(request.n)
            # Si no hay workers configurados, fallback directo local
            if num_workers == 0:
                print("[COORDINADOR] ⚠️ No hay workers configurados. Calculando sum_squares localmente.")
                total_local = sum_squares_local(1, n)
                print(f"[COORDINADOR] ✅ Resultado local sum_squares(1..{n}) = {total_local}")
                return calculo_pb2.CalculoResponse(ok=True, result=float(total_local),
                                                   parts=[calculo_pb2.Part(a=1, b=n, result=int(total_local),
                                                                          worker="coordinator_local")])

            # Dividir 1..n en num_workers partes (mismo algoritmo que antes)
            parts = num_workers
            size = n // parts
            extra = n % parts

            total = 0
            parts_result = []
            start = 1

            print(f"[COORDINADOR] Distribuyendo sumatoria entre {parts} workers")

            for i in range(parts):
                end = start + size - 1
                if i < extra:
                    end += 1

                if end < start:
                    end = start  # protección en caso n < parts

                subreq = calculo_pb2.CalculoRequest(op="sum_squares", a=start, b=end)

                # Intentar con todos los workers hasta que uno responda para este subrango
                success = False
                attempted_workers = 0
                for _ in range(max(1, num_workers)):
                    idx = next(self.rr_counter)
                    worker_addr = self.workers[idx]
                    attempted_workers += 1
                    print(f"[COORDINADOR] Intentando rango {start}..{end} en worker {worker_addr}")

                    response, used_worker = self.enviar_a_worker(subreq, worker_addr)
                    if response is None:
                        print(f"[COORDINADOR] ❌ Sin respuesta de worker {worker_addr}, probando otro")
                        continue
                    if not response.ok:
                        # Si el worker respondió con error (p. ej. rango inválido), registrarlo y seguir intentando
                        print(f"[COORDINADOR] ⚠️ Worker {used_worker} devolvió error: {response.error}")
                        continue
                    # ok
                    print(f"[COORDINADOR] ✅ Worker {used_worker} devolvió {response.result} para rango {start}..{end}")
                    total += int(response.result)
                    parts_result.append(calculo_pb2.Part(a=start, b=end, result=int(response.result), worker=used_worker))
                    success = True
                    break

                if not success:
                    # Si ningún worker pudo procesar este subrango, hacemos fallback LOCAL para este subrango
                    print(f"[COORDINADOR] ⚠️ Ningún worker procesó rango {start}..{end}. Calculando localmente ese subrango.")
                    local_res = sum_squares_local(start, end)
                    print(f"[COORDINADOR] ✅ Resultado local para {start}..{end} = {local_res}")
                    total += int(local_res)
                    parts_result.append(calculo_pb2.Part(a=start, b=end, result=int(local_res), worker="coordinator_local"))

                start = end + 1

            print(f"[COORDINADOR] ✅ Resultado final sumatoria: {total}")
            return calculo_pb2.CalculoResponse(ok=True, result=float(total), parts=parts_result)

        else:
            print(f"[COORDINADOR] ❌ Operación no soportada: {op}")
            return calculo_pb2.CalculoResponse(ok=False, error="Operación no soportada")


def serve(port, workers):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    calculo_pb2_grpc.add_CalculoServiceServicer_to_server(CalculoService(workers), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"✅ Coordinador gRPC escuchando en puerto {port} con workers: {workers}")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Uso: python calc_server_grpc.py <port> <worker1_host:port> <worker2_host:port> ...")
        sys.exit(1)

    port = int(sys.argv[1])
    workers = sys.argv[2:]

    serve(port, workers)

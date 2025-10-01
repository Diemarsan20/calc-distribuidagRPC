import grpc
from concurrent import futures
import time
import itertools

import calculo_pb2
import calculo_pb2_grpc


class CalculoService(calculo_pb2_grpc.CalculoServiceServicer):
    def __init__(self, workers):
        self.workers = workers
        self.rr_counter = itertools.cycle(range(len(workers)))  # round-robin

    def enviar_a_worker(self, request, worker_addr):
        try:
            channel = grpc.insecure_channel(worker_addr)
            stub = calculo_pb2_grpc.OperacionServiceStub(channel)
            response = stub.Calcular(request, timeout=5)
            return response, worker_addr
        except Exception as e:
            print(f"❌ Error con worker {worker_addr}: {e}")
            return None, worker_addr

    def CalculoTotal(self, request, context):
        op = request.op
        print(f"\n[COORDINADOR] Nueva operación recibida: {op}")
        print(f"[COORDINADOR] Datos recibidos -> a={request.a}, b={request.b}, n={request.n}")

        # --- operaciones básicas ---
        if op in ("add", "sub", "mul", "div"):
            for _ in range(len(self.workers)):
                idx = next(self.rr_counter)
                worker_addr = self.workers[idx]
                print(f"[COORDINADOR] Intentando operación {op} en worker {worker_addr}")

                response, used_worker = self.enviar_a_worker(request, worker_addr)
                if response and response.ok:
                    print(f"[COORDINADOR] ✅ Worker {used_worker} devolvió {response.result}")
                    return response
                elif response and not response.ok:
                    print(f"[COORDINADOR] ⚠️ Worker {used_worker} devolvió error: {response.error}")
                    return response

            print("[COORDINADOR] ❌ Ningún worker pudo procesar la operación")
            return calculo_pb2.CalculoResponse(ok=False, error="Ningún worker disponible")

        # --- sumatoria de cuadrados ---
        elif op == "sum_squares":
            n = int(request.n)
            parts = len(self.workers)
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

                subreq = calculo_pb2.CalculoRequest(op="sum_squares", a=start, b=end)

                # Intentar con todos los workers hasta que uno responda
                success = False
                for _ in range(len(self.workers)):
                    idx = next(self.rr_counter)
                    worker_addr = self.workers[idx]
                    print(f"[COORDINADOR] Intentando rango {start}..{end} en worker {worker_addr}")

                    response, used_worker = self.enviar_a_worker(subreq, worker_addr)
                    if response and response.ok:
                        print(f"[COORDINADOR] ✅ Worker {used_worker} devolvió {response.result} para rango {start}..{end}")
                        total += int(response.result)
                        parts_result.append(calculo_pb2.Part(
                            a=start, b=end, result=int(response.result), worker=used_worker
                        ))
                        success = True
                        break
                    else:
                        print(f"[COORDINADOR] ❌ Worker {worker_addr} falló en rango {start}..{end}")

                if not success:
                    print(f"[COORDINADOR] ❌ Todos los workers fallaron en rango {start}..{end}")
                    return calculo_pb2.CalculoResponse(ok=False, error="Todos los workers caídos")

                start = end + 1

            print(f"[COORDINADOR] ✅ Resultado final sumatoria: {total}")
            return calculo_pb2.CalculoResponse(ok=True, result=total, parts=parts_result)

        else:
            print(f"[COORDINADOR] ❌ Operación no soportada: {op}")
            return calculo_pb2.CalculoResponse(ok=False, error="Operación no soportada")


def serve(port, workers):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    calculo_pb2_grpc.add_CalculoServiceServicer_to_server(
        CalculoService(workers), server
    )
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

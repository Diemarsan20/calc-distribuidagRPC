import grpc
from concurrent import futures
import time

import calculo_pb2
import calculo_pb2_grpc


class OperacionService(calculo_pb2_grpc.OperacionServiceServicer):
    def Calcular(self, request, context):
        op = request.op
        a = request.a
        b = request.b
        n = request.n

        print(f"[WORKER] Solicitud recibida: op={op}, a={a}, b={b}, n={n}")

        try:
            if op == "add":
                result = a + b
            elif op == "sub":
                result = a - b
            elif op == "mul":
                result = a * b
            elif op == "div":
                if b == 0:
                    print(f"[WORKER] ❌ Error: división por cero (a={a}, b={b})")
                    return calculo_pb2.CalculoResponse(ok=False, error="División por cero")
                result = a / b
            elif op == "sum_squares":
                result = sum(i * i for i in range(int(a), int(b) + 1))
            else:
                print(f"[WORKER] ❌ Operación no soportada: {op}")
                return calculo_pb2.CalculoResponse(ok=False, error=f"Operación no soportada: {op}")

            print(f"[WORKER] ✅ Resultado: {result}")
            return calculo_pb2.CalculoResponse(ok=True, result=result, a=int(a), b=int(b))

        except Exception as e:
            print(f"[WORKER] ❌ Error inesperado: {e}")
            return calculo_pb2.CalculoResponse(ok=False, error=str(e))


def serve(port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    calculo_pb2_grpc.add_OperacionServiceServicer_to_server(
        OperacionService(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"✅ Worker gRPC escuchando en el puerto {port}")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    import sys

    port = 6001  # Valor por defecto
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    serve(port)

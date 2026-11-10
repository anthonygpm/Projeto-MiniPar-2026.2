_CPP_HEADER = """\
#include <iostream>
#include <string>
#include <sstream>
#include <vector>
#include <thread>
#include <memory>
#include <cstring>
#include <cstdio>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <type_traits>
#include <future>
#include <mutex>

#ifdef _WIN32
  #include <winsock2.h>   // inclui <windows.h> (SetThreadAffinityMask)
  #include <ws2tcpip.h>
  #pragma comment(lib, "ws2_32.lib")
  #define CLOSE_SOCK closesocket
#else
  #include <sys/socket.h>
  #include <arpa/inet.h>
  #include <unistd.h>
  #define CLOSE_SOCK close
#endif

#if defined(__linux__)
  #include <pthread.h>
  #include <sched.h>
#endif

// format(valor, casas): numero com casas decimais fixas, como f"{x:.4f}" no Python
std::string __format(double valor, int casas) {
    char buf[128];
    std::snprintf(buf, sizeof(buf), "%.*f", casas, valor);
    return std::string(buf);
}

// clock(): relogio de alta precisao em segundos (equivale a time.perf_counter()).
// So a diferenca entre duas leituras tem significado.
double __clock() {
    using namespace std::chrono;
    return duration<double>(steady_clock::now().time_since_epoch()).count();
}

// int(x): inteiro de 64 bits, truncando em direcao a zero como no Python.
// Aceita numero ou texto ("42"). O resultado e long long, entao contas como
// as do gerador LCG (estado * 1103515245 + 12345) nao estouram 32 bits.
template<typename T>
long long __int(const T& x) {
    if constexpr (std::is_constructible_v<std::string, T>) {
        return std::stoll(std::string(x));
    } else {
        return static_cast<long long>(x);
    }
}

// floor(x): maior inteiro <= x, tambem em 64 bits (math.floor do Python)
long long __floor(double x) { return static_cast<long long>(std::floor(x)); }

// Helper para Random nativo
double random_val() { return (double)rand() / RAND_MAX; }

// Helper para Input
std::string input() {
    std::string s;
    std::getline(std::cin, s);
    return s;
}

std::string input(const std::string& prompt) {
    std::cout << prompt;
    return input();
}

// Converte linha com inteiros separados por espaco em vetor (ex.: "10 -3 80")
std::vector<double> __parse_ints(const std::string& s) {
    std::vector<double> result;
    std::istringstream iss(s);
    double n;
    while (iss >> n) {
        result.push_back(n);
    }
    return result;
}

std::vector<int> __minipar_range(int end) {
    std::vector<int> values;
    for (int i = 0; i < end; ++i) values.push_back(i);
    return values;
}

std::vector<int> __minipar_range(int start, int end) {
    std::vector<int> values;
    for (int i = start; i < end; ++i) values.push_back(i);
    return values;
}

// Indexacao com verificacao de limites (lista, matriz e string).
// Indice fora da faixa encerra o programa com erro claro, em vez de
// corromper a memoria. Indices negativos contam do fim, como no Python.
[[noreturn]] inline void __index_error(long long idx, size_t size) {
    std::cerr << "[ERRO DE EXECUCAO] Indice " << idx
              << " fora dos limites (tamanho " << size << ")." << std::endl;
    std::exit(1);
}

template<typename C, typename I>
decltype(auto) __index(C&& c, I idx) {
    long long i = static_cast<long long>(idx);
    if (i < 0) i += static_cast<long long>(c.size());
    if (i < 0 || static_cast<size_t>(i) >= c.size()) __index_error(static_cast<long long>(idx), c.size());
    if constexpr (std::is_same_v<std::decay_t<C>, std::string>) {
        return std::string(1, c[static_cast<size_t>(i)]);   // s[i] devolve string de 1 caractere
    } else {
        return (c[static_cast<size_t>(i)]);                 // referencia: permite lista[i] = v
    }
}

// Helper para Arrays (.pop) do Python
template<typename T>
auto __array_pop(std::vector<T>& v) {
    if (v.empty()) return T{};
    auto val = v.back();
    v.pop_back();
    return val;
}

// Helper para formatar e printar std::vector (arrays e matrizes) nativamente
template <typename T>
std::ostream& operator<<(std::ostream& os, const std::vector<T>& v) {
    os << "[";
    for (size_t i = 0; i < v.size(); ++i) {
        os << v[i];
        if (i != v.size() - 1) os << ", ";
    }
    os << "]";
    return os;
}

template<typename T>
std::string __to_string(const T& val) {
    if constexpr (std::is_constructible_v<std::string, T>) {
        return std::string(val);
    } else {
        return std::to_string(val);
    }
}

template<typename T>
auto __make_matrix(int rows, int cols, T init_val) {
    using ActualT = std::conditional_t<std::is_same_v<std::decay_t<T>, const char*>, std::string, T>;
    return std::vector<std::vector<ActualT>>(rows, std::vector<ActualT>(cols, init_val));
}

// ======================================================================
// Fork / Join (MiniPar 2026.2)
//
//   var t = fork f(a, b) on core(n);   ->  auto t = __fork(n, [__a0 = a, __a1 = b]() { return f(__a0, __a1); });
//   var r = join t;                    ->  auto r = __join(t);
//
// Cada fork cria uma std::thread propria. O resultado volta ao pai por um
// std::promise / std::future: a thread filha cumpre a promessa ao terminar e
// o join espera a thread e le o future. Os argumentos sao copiados no momento
// do fork (a subtarefa nao compartilha as variaveis do pai).
// ======================================================================

// Fixa a thread atual no nucleo 'core' (numerados a partir de 1, como em core(1)).
// Se o programa pedir mais nucleos do que a maquina tem, o numero da a volta
// (core(9) numa CPU de 8 nucleos usa o nucleo 1). Devolve false se o SO recusar.
bool __pin_to_core(long long core) {
    unsigned total = std::thread::hardware_concurrency();
    if (core < 1 || total == 0) return false;
    unsigned idx = static_cast<unsigned>((core - 1) % total);
#if defined(_WIN32)
    if (idx >= sizeof(DWORD_PTR) * 8) return false;
    return SetThreadAffinityMask(GetCurrentThread(), static_cast<DWORD_PTR>(1) << idx) != 0;
#elif defined(__linux__)
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(idx, &set);
    return pthread_setaffinity_np(pthread_self(), sizeof(set), &set) == 0;
#else
    return false;   // macOS e outros: sem API de afinidade; o SO escolhe o nucleo
#endif
}

// Tarefa criada por fork: a thread e o future com o resultado
template<typename R>
class MiniParTask {
public:
    MiniParTask(std::thread t, std::shared_future<R> f) : thread_(std::move(t)), result_(std::move(f)) {}
    MiniParTask(const MiniParTask&) = delete;
    MiniParTask& operator=(const MiniParTask&) = delete;

    // Como no multiprocessing do Python, o programa espera as tarefas que
    // ninguem aguardou com join antes de terminar.
    ~MiniParTask() { wait(); }

    R join() {
        wait();
        return result_.get();
    }

private:
    void wait() {
        std::lock_guard<std::mutex> lock(mutex_);
        if (thread_.joinable()) thread_.join();
    }
    std::thread thread_;
    std::shared_future<R> result_;
    std::mutex mutex_;
};

// core <= 0: sem destino (o sistema operacional escolhe o nucleo)
template<typename F>
auto __fork(long long core, F subtarefa) {
    using Ret = std::invoke_result_t<F&>;
    // Subtarefa sem retorno (void) devolve 0 no join
    using R = std::conditional_t<std::is_void_v<Ret>, long long, std::decay_t<Ret>>;
    std::promise<R> promessa;
    std::shared_future<R> futuro = promessa.get_future().share();
    std::thread filha([core, subtarefa = std::move(subtarefa), promessa = std::move(promessa)]() mutable {
        if (core > 0) __pin_to_core(core);
        try {
            if constexpr (std::is_void_v<Ret>) {
                subtarefa();
                promessa.set_value(0);
            } else {
                promessa.set_value(subtarefa());
            }
        } catch (...) {
            promessa.set_exception(std::current_exception());
        }
    });
    return std::make_shared<MiniParTask<R>>(std::move(filha), futuro);
}

template<typename R>
R __join(const std::shared_ptr<MiniParTask<R>>& tarefa) { return tarefa->join(); }

// "fork f();" sem guardar a tarefa: ela continua rodando e e aguardada no fim do programa
std::vector<std::shared_ptr<void>>& __detached_tasks() {
    static std::vector<std::shared_ptr<void>> tarefas;
    return tarefas;
}
std::mutex __detached_mutex;
template<typename T>
void __keep_running(std::shared_ptr<T> tarefa) {
    std::lock_guard<std::mutex> lock(__detached_mutex);
    __detached_tasks().push_back(std::move(tarefa));
}

// Tipo dos elementos de uma lista criada vazia ([]) e preenchida com append:
// numeros continuam double (como as listas literais); tarefas, textos e
// listas mantem o proprio tipo.
template<typename T>
using __list_elem_t = std::conditional_t<std::is_arithmetic_v<std::decay_t<T>>, double, std::decay_t<T>>;

class MiniParChannel {
public:
    std::string ip;
    int port;

    MiniParChannel(std::string ip, int port) : ip(ip), port(port) {}

    void sendData(std::string msg) {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) return;
        struct sockaddr_in serv_addr;
        serv_addr.sin_family = AF_INET;
        serv_addr.sin_port = htons(port);
        inet_pton(AF_INET, ip.c_str(), &serv_addr.sin_addr);
        
        for(int i=0; i<50; i++) {
            if (connect(sock, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) >= 0) {
                send(sock, msg.c_str(), msg.length(), 0);
                break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        CLOSE_SOCK(sock);
    }

    std::string receiveData() {
        int server_fd = socket(AF_INET, SOCK_STREAM, 0);
        if (server_fd < 0) return "";
        int opt = 1;
        setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));
        
        struct sockaddr_in address;
        address.sin_family = AF_INET;
        address.sin_addr.s_addr = INADDR_ANY;
        address.sin_port = htons(port);
        
        if (bind(server_fd, (struct sockaddr*)&address, sizeof(address)) < 0) { CLOSE_SOCK(server_fd); return ""; }
        if (listen(server_fd, 3) < 0) { CLOSE_SOCK(server_fd); return ""; }
        
        int new_socket = accept(server_fd, nullptr, nullptr);
        if (new_socket < 0) { CLOSE_SOCK(server_fd); return ""; }
        
        char buffer[4096] = {0};
        recv(new_socket, buffer, 4096, 0);
        std::string result(buffer);
        
        CLOSE_SOCK(new_socket);
        CLOSE_SOCK(server_fd);
        return result;
    }
};

"""

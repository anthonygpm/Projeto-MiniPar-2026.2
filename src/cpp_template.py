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
long long __mp_floor(double x) { return static_cast<long long>(std::floor(x)); }

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

# ============================================================================
# Fork para outro computador: fork f(args) on host(ip, porta)  (MiniPar 2026.2)
#
# O outro computador roda o MESMO executavel com "--worker <porta>". Cada
# "fork f(args) on host(...)" registra, na compilacao, uma entrada f(tipos)
# que o worker sabe executar. O pai envia o nome registrado e os argumentos
# (MPValue serializado), o worker executa e devolve o resultado.
#
# Do lado do pai, a subtarefa e um __fork comum (thread local) cuja tarefa e
# fazer a chamada remota: o join e a lista de tarefas funcionam igual aos
# forks em nucleo.
# ============================================================================
_CPP_HEADER += r"""
#include <map>
#include <cstdint>
#include <stdexcept>
#include <utility>
#ifndef _WIN32
  #include <netdb.h>
  #include <netinet/in.h>
#endif

// ---------------------------------------------------------------------------
// MPValue: valor dinamico que atravessa a rede (numero, texto, bool ou lista)
// ---------------------------------------------------------------------------
template<typename T> struct __mp_is_vector : std::false_type {};
template<typename U, typename A> struct __mp_is_vector<std::vector<U, A>> : std::true_type {};

struct MPValue {
    enum class Kind { None, Int, Num, Str, Bool, List };
    Kind kind = Kind::None;
    long long i = 0;
    double d = 0.0;
    bool b = false;
    std::string s;
    std::vector<MPValue> list;

    // Constroi a partir de um valor do programa gerado
    template<typename T>
    static MPValue from(const T& x) {
        using D = std::decay_t<T>;
        MPValue v;
        if constexpr (std::is_same_v<D, MPValue>) { return x; }
        else if constexpr (std::is_same_v<D, bool>) { v.kind = Kind::Bool; v.b = x; }
        else if constexpr (std::is_integral_v<D>) { v.kind = Kind::Int; v.i = static_cast<long long>(x); }
        else if constexpr (std::is_floating_point_v<D>) { v.kind = Kind::Num; v.d = static_cast<double>(x); }
        else if constexpr (std::is_constructible_v<std::string, D>) { v.kind = Kind::Str; v.s = std::string(x); }
        else if constexpr (__mp_is_vector<D>::value) {
            v.kind = Kind::List;
            for (const auto& e : x) v.list.push_back(MPValue::from(e));
        }
        else { static_assert(sizeof(D) == 0, "fork para host: tipo nao suportado (use numero, string, bool ou lista)"); }
        return v;
    }

    double num() const {
        switch (kind) {
            case Kind::Int:  return static_cast<double>(i);
            case Kind::Num:  return d;
            case Kind::Bool: return b ? 1.0 : 0.0;
            case Kind::Str:  return std::stod(s);
            default:         return 0.0;
        }
    }
    std::string text() const;

    // Converte de volta para o tipo que o programa gerado espera
    template<typename T>
    T as() const {
        using D = std::decay_t<T>;
        if constexpr (std::is_same_v<D, MPValue>) { return *this; }
        else if constexpr (std::is_same_v<D, bool>) {
            if (kind == Kind::Str) return !s.empty();
            if (kind == Kind::List) return !list.empty();
            return num() != 0.0;
        }
        else if constexpr (std::is_integral_v<D>) { return kind == Kind::Int ? static_cast<D>(i) : static_cast<D>(num()); }
        else if constexpr (std::is_floating_point_v<D>) { return static_cast<D>(num()); }
        else if constexpr (std::is_same_v<D, std::string>) { return text(); }
        else if constexpr (__mp_is_vector<D>::value) {
            D out;
            for (const auto& e : list) out.push_back(e.template as<typename D::value_type>());
            return out;
        }
        else { static_assert(sizeof(D) == 0, "fork para host: conversao nao suportada"); }
    }
};

inline std::ostream& operator<<(std::ostream& os, const MPValue& v) {
    switch (v.kind) {
        case MPValue::Kind::Int:  os << v.i; break;
        case MPValue::Kind::Num:  os << v.d; break;
        case MPValue::Kind::Bool: os << v.b; break;
        case MPValue::Kind::Str:  os << v.s; break;
        case MPValue::Kind::List:
            os << "[";
            for (size_t k = 0; k < v.list.size(); ++k) { if (k) os << ", "; os << v.list[k]; }
            os << "]";
            break;
        default: os << "None"; break;
    }
    return os;
}
inline std::string MPValue::text() const {
    if (kind == Kind::Str) return s;
    std::ostringstream os; os << *this; return os.str();
}

// ---------------------------------------------------------------------------
// Serializacao (texto com tamanhos explicitos, seguro para a rede)
//   z  nenhum valor   i<n>;  inteiro   n<x>;  ponto flutuante   b0 / b1  bool
//   s<len>:<bytes>    texto            l<qtd>:<elementos...>     lista
// ---------------------------------------------------------------------------
inline void __mp_serialize_into(const MPValue& v, std::string& out) {
    switch (v.kind) {
        case MPValue::Kind::None: out += 'z'; break;
        case MPValue::Kind::Int:  out += 'i'; out += std::to_string(v.i); out += ';'; break;
        case MPValue::Kind::Num: {
            char buf[64]; std::snprintf(buf, sizeof(buf), "%.17g", v.d);
            out += 'n'; out += buf; out += ';'; break;
        }
        case MPValue::Kind::Bool: out += v.b ? "b1" : "b0"; break;
        case MPValue::Kind::Str:  out += 's'; out += std::to_string(v.s.size()); out += ':'; out += v.s; break;
        case MPValue::Kind::List:
            out += 'l'; out += std::to_string(v.list.size()); out += ':';
            for (const auto& e : v.list) __mp_serialize_into(e, out);
            break;
    }
}
inline std::string __mp_serialize(const MPValue& v) { std::string out; __mp_serialize_into(v, out); return out; }

inline MPValue __mp_parse(const std::string& in, size_t& p) {
    auto fail = [] { throw std::runtime_error("mensagem de fork corrompida"); };
    auto read_until = [&](char end) {
        size_t q = in.find(end, p);
        if (q == std::string::npos) fail();
        std::string part = in.substr(p, q - p); p = q + 1; return part;
    };
    if (p >= in.size()) fail();
    char tag = in[p++];
    MPValue v;
    switch (tag) {
        case 'z': break;
        case 'i': v.kind = MPValue::Kind::Int; v.i = std::stoll(read_until(';')); break;
        case 'n': v.kind = MPValue::Kind::Num; v.d = std::stod(read_until(';')); break;
        case 'b': if (p >= in.size()) fail(); v.kind = MPValue::Kind::Bool; v.b = in[p++] == '1'; break;
        case 's': {
            size_t len = std::stoull(read_until(':'));
            if (p + len > in.size()) fail();
            v.kind = MPValue::Kind::Str; v.s = in.substr(p, len); p += len; break;
        }
        case 'l': {
            size_t count = std::stoull(read_until(':'));
            v.kind = MPValue::Kind::List;
            for (size_t k = 0; k < count; ++k) v.list.push_back(__mp_parse(in, p));
            break;
        }
        default: fail();
    }
    return v;
}
inline MPValue __mp_deserialize(const std::string& in) {
    size_t p = 0; MPValue v = __mp_parse(in, p);
    if (p != in.size()) throw std::runtime_error("mensagem de fork com dados sobrando");
    return v;
}

// ---------------------------------------------------------------------------
// Sockets: mensagem = 4 bytes de tamanho (ordem de rede) + conteudo
// ---------------------------------------------------------------------------
#ifdef _WIN32
  using __mp_sock_t = SOCKET;
  #define __MP_BAD_SOCK INVALID_SOCKET
#else
  using __mp_sock_t = int;
  #define __MP_BAD_SOCK (-1)
#endif
#ifdef MSG_NOSIGNAL
  #define __MP_SEND_FLAGS MSG_NOSIGNAL
#else
  #define __MP_SEND_FLAGS 0
#endif

inline bool __mp_send_all(__mp_sock_t sock, const char* data, size_t len) {
    while (len > 0) {   // TCP pode aceitar so parte dos bytes por vez
        int n = send(sock, data, static_cast<int>(len), __MP_SEND_FLAGS);
        if (n <= 0) return false;
        data += n; len -= static_cast<size_t>(n);
    }
    return true;
}
inline bool __mp_recv_all(__mp_sock_t sock, char* data, size_t len) {
    while (len > 0) {
        int n = recv(sock, data, static_cast<int>(len), 0);
        if (n <= 0) return false;
        data += n; len -= static_cast<size_t>(n);
    }
    return true;
}
inline bool __mp_send_frame(__mp_sock_t sock, const std::string& msg) {
    unsigned char hdr[4];
    uint32_t n = static_cast<uint32_t>(msg.size());
    hdr[0] = (n >> 24) & 0xFF; hdr[1] = (n >> 16) & 0xFF; hdr[2] = (n >> 8) & 0xFF; hdr[3] = n & 0xFF;
    return __mp_send_all(sock, reinterpret_cast<const char*>(hdr), 4) && __mp_send_all(sock, msg.data(), msg.size());
}
inline bool __mp_recv_frame(__mp_sock_t sock, std::string& msg) {
    unsigned char hdr[4];
    if (!__mp_recv_all(sock, reinterpret_cast<char*>(hdr), 4)) return false;
    uint32_t n = (uint32_t(hdr[0]) << 24) | (uint32_t(hdr[1]) << 16) | (uint32_t(hdr[2]) << 8) | uint32_t(hdr[3]);
    if (n > (256u << 20)) return false;     // limite de 256 MB por mensagem
    msg.assign(n, '\0');
    return n == 0 || __mp_recv_all(sock, msg.data(), n);
}

// ---------------------------------------------------------------------------
// Registro das funcoes que o worker pode executar: "f(tipos)" -> executor
// ---------------------------------------------------------------------------
using __mp_handler_t = MPValue (*)(const std::vector<MPValue>&);
inline std::map<std::string, __mp_handler_t>& __mp_registry() {
    static std::map<std::string, __mp_handler_t> r;
    return r;
}

// Nome de tipo estavel, igual nos dois computadores (ex.: "i64", "s", "Ls")
template<typename T>
std::string __mp_type_tag() {
    using D = std::decay_t<T>;
    if constexpr (std::is_same_v<D, bool>) return "b";
    else if constexpr (std::is_integral_v<D>) return (std::is_signed_v<D> ? "i" : "u") + std::to_string(sizeof(D) * 8);
    else if constexpr (std::is_floating_point_v<D>) return "f" + std::to_string(sizeof(D) * 8);
    else if constexpr (std::is_same_v<D, std::string>) return "s";
    else if constexpr (__mp_is_vector<D>::value) return "L" + __mp_type_tag<typename D::value_type>();
    else { static_assert(sizeof(D) == 0, "fork para host: argumento de tipo nao suportado"); return ""; }
}

// Uma entrada de registro por combinacao (funcao, tipos dos argumentos)
template<typename F, typename... A>
struct __MPRemote {
    static std::string key() {
        std::string k = F::name; k += "(";
        bool first = true;
        ((k += (first ? "" : ","), k += __mp_type_tag<A>(), first = false), ...);
        return k + ")";
    }
    template<size_t... I>
    static MPValue call(const std::vector<MPValue>& args, std::index_sequence<I...>) {
        if (args.size() != sizeof...(A)) throw std::runtime_error("numero de argumentos diferente do esperado");
        using Ret = decltype(F{}(std::declval<A>()...));
        if constexpr (std::is_void_v<Ret>) { F{}(args[I].template as<A>()...); return MPValue{}; }
        else { return MPValue::from(F{}(args[I].template as<A>()...)); }
    }
    static MPValue handle(const std::vector<MPValue>& args) { return call(args, std::index_sequence_for<A...>{}); }
    // Inicializado antes do main: o worker ja conhece a funcao ao subir
    static inline const bool registered = (__mp_registry()[key()] = &handle, true);
};

// ---------------------------------------------------------------------------
// Lado do pai: conecta ao worker, envia o pedido e espera a resposta
// ---------------------------------------------------------------------------
inline __mp_sock_t __mp_connect(const std::string& ip, int port) {
    addrinfo hints{}; hints.ai_family = AF_INET; hints.ai_socktype = SOCK_STREAM;
    addrinfo* res = nullptr;
    if (getaddrinfo(ip.c_str(), std::to_string(port).c_str(), &hints, &res) != 0 || !res)
        throw std::runtime_error("endereco invalido: " + ip);
    for (int tentativa = 0; tentativa < 50; ++tentativa) {      // ate ~5 s esperando o worker subir
        __mp_sock_t sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock != __MP_BAD_SOCK) {
            if (connect(sock, res->ai_addr, static_cast<int>(res->ai_addrlen)) == 0) { freeaddrinfo(res); return sock; }
            CLOSE_SOCK(sock);
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    freeaddrinfo(res);
    throw std::runtime_error("nao foi possivel conectar a " + ip + ":" + std::to_string(port) +
                             ". O worker esta rodando? Execute nesse computador: <programa> --worker " + std::to_string(port));
}

inline MPValue __mp_remote_call(const std::string& ip, int port, const std::string& key, const std::vector<MPValue>& args) {
    MPValue req; req.kind = MPValue::Kind::List;
    req.list.push_back(MPValue::from(key));
    MPValue packed; packed.kind = MPValue::Kind::List; packed.list = args;
    req.list.push_back(packed);
    __mp_sock_t sock = __mp_connect(ip, port);
    std::string reply;
    bool ok = __mp_send_frame(sock, __mp_serialize(req)) && __mp_recv_frame(sock, reply);
    CLOSE_SOCK(sock);
    if (!ok) throw std::runtime_error("conexao com " + ip + ":" + std::to_string(port) + " interrompida");
    MPValue resp = __mp_deserialize(reply);
    if (resp.kind != MPValue::Kind::List || resp.list.size() != 2 || resp.list[0].kind != MPValue::Kind::Str)
        throw std::runtime_error("resposta invalida do worker");
    if (resp.list[0].s != "ok") throw std::runtime_error("o worker respondeu: " + resp.list[1].text());
    return resp.list[1];
}

// fork f(args) on host(ip, porta): devolve a mesma tarefa de um __fork em nucleo
template<typename F, typename... A>
auto __fork_host(const std::string& ip, long long port, const A&... args) {
    using Rem = __MPRemote<F, std::decay_t<A>...>;
    (void)Rem::registered;                                   // garante o registro no executavel
    using Ret = decltype(F{}(std::declval<std::decay_t<A>>()...));
    std::string key = Rem::key();
    std::vector<MPValue> vals{ MPValue::from(args)... };
    int p = static_cast<int>(port);
    return __fork(0, [ip, p, key, vals]() {
        MPValue r;
        try {
            r = __mp_remote_call(ip, p, key, vals);
        } catch (const std::exception& e) {
            // Falha na rede ou no worker: encerra com mensagem clara (como um erro de execucao)
            std::cout << std::flush;
            std::cerr << "[ERRO DE EXECUCAO] Subtarefa '" << std::string(F::name) << "' em " << ip << ":" << p
                      << " falhou: " << e.what() << std::endl;
            std::_Exit(1);
        }
        if constexpr (!std::is_void_v<Ret>) return r.template as<std::decay_t<Ret>>();
    });
}

// ---------------------------------------------------------------------------
// Lado do worker: "programa --worker 5001"
// ---------------------------------------------------------------------------
inline void __mp_log(const std::string& line) {   // uma linha por vez (pedidos rodam em paralelo)
    static std::mutex m;
    std::lock_guard<std::mutex> lock(m);
    std::cout << line << std::endl;
}

// Atende um pedido: executa a funcao registrada e devolve "ok" ou "erro"
inline void __mp_worker_serve(__mp_sock_t client, std::string who) {
    std::string msg;
    if (!__mp_recv_frame(client, msg)) { CLOSE_SOCK(client); return; }
    MPValue resp; resp.kind = MPValue::Kind::List;
    try {
        MPValue req = __mp_deserialize(msg);
        if (req.kind != MPValue::Kind::List || req.list.size() != 2) throw std::runtime_error("pedido invalido");
        std::string key = req.list[0].text();
        auto it = __mp_registry().find(key);
        if (it == __mp_registry().end())
            throw std::runtime_error("funcao " + key + " nao existe neste executavel; compile o mesmo programa nos dois computadores");
        __mp_log("[WORKER] Executando " + key + " pedida por " + who);
        auto t0 = std::chrono::steady_clock::now();
        MPValue result = it->second(req.list[1].list);
        double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        __mp_log("[WORKER] " + key + " concluida em " + __format(secs, 2) + " s");
        resp.list.push_back(MPValue::from(std::string("ok")));
        resp.list.push_back(result);
    } catch (const std::exception& e) {
        __mp_log(std::string("[WORKER] Erro: ") + e.what());
        resp.list.clear();
        resp.list.push_back(MPValue::from(std::string("erro")));
        resp.list.push_back(MPValue::from(std::string(e.what())));
    }
    __mp_send_frame(client, __mp_serialize(resp));
    CLOSE_SOCK(client);
}

inline int __mp_worker_main(int port) {
    __mp_sock_t server = socket(AF_INET, SOCK_STREAM, 0);
    if (server == __MP_BAD_SOCK) { std::cerr << "[WORKER] Nao foi possivel criar o socket." << std::endl; return 1; }
    int opt = 1;
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));
    sockaddr_in addr{}; addr.sin_family = AF_INET; addr.sin_addr.s_addr = INADDR_ANY; addr.sin_port = htons(port);
    if (bind(server, (sockaddr*)&addr, sizeof(addr)) < 0 || listen(server, 16) < 0) {
        std::cerr << "[WORKER] Porta " << port << " indisponivel (ja esta em uso?)." << std::endl;
        CLOSE_SOCK(server); return 1;
    }
    std::cout << "[WORKER] Aguardando subtarefas na porta " << port << " (Ctrl+C para encerrar)" << std::endl;
    std::cout << "[WORKER] Funcoes disponiveis:";
    if (__mp_registry().empty()) std::cout << " nenhuma (o programa nao tem fork ... on host)";
    for (const auto& [k, h] : __mp_registry()) std::cout << " " << k;
    std::cout << std::endl;
    while (true) {   // cada pedido numa thread: varias subtarefas rodam ao mesmo tempo
        sockaddr_in peer{};
        socklen_t peer_len = sizeof(peer);
        __mp_sock_t client = accept(server, (sockaddr*)&peer, &peer_len);
        if (client == __MP_BAD_SOCK) continue;
        char ipbuf[64] = "?";
        inet_ntop(AF_INET, &peer.sin_addr, ipbuf, sizeof(ipbuf));
        std::thread(__mp_worker_serve, client, std::string(ipbuf)).detach();
    }
}

// "programa --worker 5001" entra em modo worker; senao devolve -1 e o programa roda normal
inline int __mp_worker_from_args(int argc, char** argv) {
    for (int k = 1; k < argc; ++k) {
        if (std::string(argv[k]) == "--worker") {
            if (k + 1 >= argc) { std::cerr << "Uso: " << argv[0] << " --worker <porta>" << std::endl; return 1; }
            return __mp_worker_main(std::atoi(argv[k + 1]));
        }
    }
    return -1;
}
"""

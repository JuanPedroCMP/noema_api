# Configuração de provedores e modelos de IA

## Preparação

1. Faça backup do banco e aplique `migrations/20261103_user_ai_providers.sql` como uma única transação antes de iniciar a nova versão da API.
2. Configure `ADMIN_EMAIL` no ambiente do backend com o e-mail exato da única conta que pode alterar o catálogo global. Sem essa variável, as alterações globais retornam `503`; outras contas recebem `403`.
3. Faça login normalmente e envie o token Bearer nas rotas de escrita.

As rotas públicas existentes de consulta (`GET /api/v1/ai/provider`, `ai_model`, `agent` e `agent_model`) continuam sem autenticação, mas agora expõem somente registros globais. As rotas de leitura pessoal também exigem autenticação para não revelar configurações dos demais usuários.

## Configuração pessoal

Todas as rotas abaixo exigem autenticação e só permitem alterar dados pertencentes à conta autenticada. Listas incluem os recursos globais visíveis e os pessoais:

| Recurso | Rotas |
|---|---|
| Provedores | `GET/POST /api/v1/ai/me/providers`, `GET/PUT/DELETE /api/v1/ai/me/providers/{id}` |
| Modelos | `GET/POST /api/v1/ai/me/models`, `GET/PUT/DELETE /api/v1/ai/me/models/{id}` |
| Agentes | `GET/POST /api/v1/ai/me/agents`, `GET/PUT/DELETE /api/v1/ai/me/agents/{id}` |
| Modelos de agente | `GET/POST /api/v1/ai/me/agent-models`, `GET/PUT/DELETE /api/v1/ai/me/agent-models/{id}` |

Para usar um modelo com autenticação, crie o provedor e o modelo, cadastre uma chave pela rota autenticada `/api/v1/ai/user_api_key/create` e vincule a chave ao modelo por `/api/v1/ai/user_api_key_can_use_ia_model/create`. Provedores OpenAI-compatible locais aceitam chave vazia. Chaves são criptografadas no banco e nunca retornadas pelas rotas de consulta.

Provedores pessoais usam o protocolo `openai_compatible`, incluindo serviços compatíveis com a API OpenAI, como vLLM, LM Studio, LocalAI, llama.cpp server e Ollama com a API OpenAI ativada. Informe o `base_url` completo, normalmente terminado em `/v1`.

Por padrão, endpoints devem usar HTTPS e IPs privados/reservados são recusados, inclusive após resolução DNS. Em produção pública, configure também egress/firewall para bloquear redes internas, link-local e endpoints de metadata: a validação DNS na aplicação não substitui esse controle de rede. Para um backend executado na mesma máquina que o modelo local, habilite `AI_ALLOW_LOCAL_AI=true`; isso libera loopback e IPs privados literais também via HTTP. Use essa opção apenas em instalações confiáveis e com controles de egress adequados. Exclusões de provedores, modelos, agentes, vínculos e chaves são lógicas: os registros são desativados para preservar histórico e referências no banco. Em um backend hospedado remotamente, `localhost` aponta para o próprio servidor, não para o PC do usuário; alcançar um modelo no PC do usuário requer um canal cliente/servidor ou túnel seguro fora destas rotas.

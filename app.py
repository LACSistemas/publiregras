import streamlit as st
import requests
import time
import json
import pandas as pd
from datetime import datetime, date
import hashlib
from typing import List, Dict, Any, Optional
import math
from dataclasses import dataclass
from enum import Enum
 
# === CONFIGURAÇÃO ===
st.set_page_config(
    page_title="Automação de buscas pelo DJEN- CNJ",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

class RuleType(Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"

class RuleOperator(Enum):
    AND = "and"
    OR = "or"

@dataclass
class SearchRule:
    name: str
    rule_type: RuleType
    operator: RuleOperator
    enabled: bool
    parameters: Dict[str, Any]
    
    def __post_init__(self):
        # Remove empty parameters
        self.parameters = {k: v for k, v in self.parameters.items() if v is not None and v != ""}

# === ESTILO CSS ===
st.markdown("""
<style>
    .publication-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 20px;
        margin: 10px 0;
        background-color: #f9f9f9;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .publication-title {
        font-size: 18px;
        font-weight: bold;
        color: #1f4e79;
        margin-bottom: 10px;
    }
    .publication-info {
        font-size: 14px;
        color: #666;
        margin-bottom: 8px;
    }
    .publication-text {
        background-color: #fff;
        padding: 15px;
        border-radius: 4px;
        border-left: 4px solid #1f4e79;
        margin: 10px 0;
        font-size: 14px;
        line-height: 1.5;
    }
    .lawyer-info {
        background-color: #e8f4f8;
        padding: 10px;
        border-radius: 4px;
        margin: 5px 0;
        font-size: 13px;
    }
    .search-progress {
        text-align: center;
        padding: 20px;
        background-color: #e8f4f8;
        border-radius: 8px;
        margin: 10px 0;
    }
    .rule-card {
        border: 1px solid #ccc;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
        background-color: #fafafa;
    }
    .rule-include {
        border-left: 4px solid #28a745;
    }
    .rule-exclude {
        border-left: 4px solid #dc3545;
    }
    .rule-disabled {
        opacity: 0.6;
        background-color: #f8f9fa;
    }
</style>
""", unsafe_allow_html=True)

class EnhancedDJESearcher:
    def __init__(self):
        self.base_url = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
        self.all_publications = []
        
    def search_with_params(self, params: Dict[str, Any], progress_callback=None) -> List[Dict]:
        """Executa busca com parâmetros específicos"""
        publications = []
        search_params = params.copy()
        search_params.update({
            "itensPorPagina": 50,
            "pagina": 1
        })
        
        rule_name = params.get('_rule_name', 'Busca')
        
        while True:
            if progress_callback:
                progress_callback(f"Executando {rule_name} - Página {search_params['pagina']}")
            
            try:
                response = requests.get(self.base_url, params=search_params, timeout=30)
                
                if response.status_code == 200:
                    dados = response.json()
                    items = dados.get("items", [])
                    
                    if not items:
                        break
                    
                    publications.extend(items)
                    search_params["pagina"] += 1
                    time.sleep(0.5)  # Rate limiting
                    
                elif response.status_code == 429:
                    if progress_callback:
                        progress_callback("Rate limit atingido. Aguardando...")
                    time.sleep(10)
                else:
                    st.error(f"Erro na busca {rule_name}: {response.status_code}")
                    break
                    
            except Exception as e:
                st.error(f"Erro na requisição {rule_name}: {str(e)}")
                break
                
        return publications
    
    def execute_rules(self, rules: List[SearchRule], progress_callback=None) -> List[Dict]:
        """Executa todas as regras e combina os resultados"""
        include_publications = []
        exclude_publications = []
        
        for rule in rules:
            if not rule.enabled:
                continue
                
            if progress_callback:
                progress_callback(f"Executando regra: {rule.name}")
            
            # Adiciona identificador da regra nos parâmetros
            rule_params = rule.parameters.copy()
            rule_params['_rule_name'] = rule.name
            
            publications = self.search_with_params(rule_params, progress_callback)
            
            if rule.rule_type == RuleType.INCLUDE:
                if rule.operator == RuleOperator.OR:
                    include_publications.extend(publications)
                else:  # AND
                    if not include_publications:
                        include_publications = publications
                    else:
                        # Intersecção baseada em hash
                        include_hashes = {pub.get('hash', pub.get('id', '')) for pub in include_publications}
                        publications_hashes = {pub.get('hash', pub.get('id', '')) for pub in publications}
                        common_hashes = include_hashes.intersection(publications_hashes)
                        include_publications = [pub for pub in include_publications 
                                              if pub.get('hash', pub.get('id', '')) in common_hashes]
            
            elif rule.rule_type == RuleType.EXCLUDE:
                exclude_publications.extend(publications)
        
        # Remove duplicatas das inclusões
        if progress_callback:
            progress_callback("Removendo duplicatas das inclusões...")
        include_publications = self.remove_duplicates(include_publications)
        
        # Remove as exclusões
        if exclude_publications:
            if progress_callback:
                progress_callback("Aplicando exclusões...")
            exclude_hashes = {pub.get('hash', pub.get('id', '')) for pub in exclude_publications}
            final_publications = [pub for pub in include_publications 
                                if pub.get('hash', pub.get('id', '')) not in exclude_hashes]
        else:
            final_publications = include_publications
        
        return final_publications
    
    def remove_duplicates(self, publications: List[Dict]) -> List[Dict]:
        """Remove duplicatas baseado no hash da publicação"""
        seen_hashes = set()
        unique_publications = []
        
        for pub in publications:
            pub_hash = pub.get('hash')
            if pub_hash and pub_hash not in seen_hashes:
                seen_hashes.add(pub_hash)
                unique_publications.append(pub)
            elif not pub_hash:
                # Para publicações sem hash, usar outros campos para identificar duplicatas
                unique_id = f"{pub.get('id', '')}_{pub.get('numeroprocessocommascara', '')}"
                if unique_id not in seen_hashes:
                    seen_hashes.add(unique_id)
                    unique_publications.append(pub)
        
        return unique_publications

def create_rule_form(rule_index: int, existing_rule: Optional[SearchRule] = None) -> Optional[SearchRule]:
    """Cria formulário para configurar uma regra"""
    prefix = f"rule_{rule_index}"
    
    with st.expander(f"📋 Regra {rule_index + 1}" + (f" - {existing_rule.name}" if existing_rule else ""), expanded=not existing_rule):
        col1, col2 = st.columns(2)
        
        with col1:
            rule_name = st.text_input(
                "Nome da Regra", 
                value=existing_rule.name if existing_rule else f"Regra {rule_index + 1}",
                key=f"{prefix}_name"
            )
            
            # Fixed rule type selection with proper key handling
            rule_type_options = [RuleType.INCLUDE, RuleType.EXCLUDE]
            
            if existing_rule:
                try:
                    default_index = rule_type_options.index(existing_rule.rule_type)
                except ValueError:
                    default_index = 0
            else:
                default_index = 0
            
            rule_type = st.selectbox(
                "Tipo de Regra",
                options=rule_type_options,
                format_func=lambda x: "Incluir" if x == RuleType.INCLUDE else "Excluir",
                index=default_index,
                key=f"{prefix}_type"
            )
        
        with col2:
            # Fixed operator selection with proper key handling
            operator_options = [RuleOperator.OR, RuleOperator.AND]
            
            if existing_rule:
                try:
                    operator_index = operator_options.index(existing_rule.operator)
                except ValueError:
                    operator_index = 0
            else:
                operator_index = 0
            
            rule_operator = st.selectbox(
                "Operador (para regras do tipo Incluir)",
                options=operator_options,
                format_func=lambda x: "OU (união)" if x == RuleOperator.OR else "E (interseção)",
                index=operator_index,
                key=f"{prefix}_operator",
                disabled=rule_type == RuleType.EXCLUDE
            )
            
            rule_enabled = st.checkbox(
                "Regra Ativa",
                value=existing_rule.enabled if existing_rule else True,
                key=f"{prefix}_enabled"
            )
        
        st.markdown("**Parâmetros de Busca:**")
        
        # Parâmetros organizados em colunas
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**👨‍💼 Advogado/OAB**")
            numero_oab = st.text_input(
                "Número da OAB",
                value=existing_rule.parameters.get('numeroOab', '') if existing_rule else '',
                key=f"{prefix}_numero_oab"
            )
            
            uf_options = [""] + ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]
            uf_default = 0
            if existing_rule and existing_rule.parameters.get('ufOab'):
                try:
                    uf_default = uf_options.index(existing_rule.parameters.get('ufOab'))
                except ValueError:
                    uf_default = 0
            
            uf_oab = st.selectbox(
                "UF da OAB",
                options=uf_options,
                index=uf_default,
                key=f"{prefix}_uf_oab"
            )
            
            nome_advogado = st.text_input(
                "Nome do Advogado",
                value=existing_rule.parameters.get('nomeAdvogado', '') if existing_rule else '',
                key=f"{prefix}_nome_advogado"
            )
        
        with col2:
            st.markdown("**👥 Parte/Processo**")
            nome_parte = st.text_input(
                "Nome da Parte",
                value=existing_rule.parameters.get('nomeParte', '') if existing_rule else '',
                key=f"{prefix}_nome_parte"
            )
            
            numero_processo = st.text_input(
                "Número do Processo",
                value=existing_rule.parameters.get('numeroProcesso', '') if existing_rule else '',
                key=f"{prefix}_numero_processo"
            )
            
            numero_comunicacao = st.number_input(
                "Número da Comunicação",
                min_value=0,
                value=existing_rule.parameters.get('numeroComunicacao', 0) if existing_rule else 0,
                key=f"{prefix}_numero_comunicacao"
            )
        
        with col3:
            st.markdown("**🏛️ Tribunal/Órgão**")
            sigla_tribunal = st.text_input(
                "Sigla do Tribunal",
                value=existing_rule.parameters.get('siglaTribunal', '') if existing_rule else '',
                key=f"{prefix}_sigla_tribunal"
            )
            
            orgao_id = st.number_input(
                "ID do Órgão",
                min_value=0,
                value=existing_rule.parameters.get('orgaoId', 0) if existing_rule else 0,
                key=f"{prefix}_orgao_id"
            )
        
        st.markdown("**📅 Período**")
        col1, col2 = st.columns(2)
        
        with col1:
            default_start_date = date(2025, 7, 7)
            if existing_rule and existing_rule.parameters.get('dataDisponibilizacaoInicio'):
                try:
                    default_start_date = datetime.strptime(existing_rule.parameters.get('dataDisponibilizacaoInicio'), '%Y-%m-%d').date()
                except ValueError:
                    default_start_date = date(2025, 7, 7)
            
            data_inicio = st.date_input(
                "Data de Início",
                value=default_start_date,
                key=f"{prefix}_data_inicio"
            )
        
        with col2:
            default_end_date = None
            if existing_rule and existing_rule.parameters.get('dataDisponibilizacaoFim'):
                try:
                    default_end_date = datetime.strptime(existing_rule.parameters.get('dataDisponibilizacaoFim'), '%Y-%m-%d').date()
                except ValueError:
                    default_end_date = None
            
            data_fim = st.date_input(
                "Data de Fim",
                value=default_end_date,
                key=f"{prefix}_data_fim"
            )
        
        # Cria parâmetros
        parameters = {}
        
        if numero_oab:
            parameters['numeroOab'] = numero_oab
        if uf_oab:
            parameters['ufOab'] = uf_oab
        if nome_advogado:
            parameters['nomeAdvogado'] = nome_advogado
        if nome_parte:
            parameters['nomeParte'] = nome_parte
        if numero_processo:
            parameters['numeroProcesso'] = numero_processo
        if numero_comunicacao > 0:
            parameters['numeroComunicacao'] = numero_comunicacao
        if sigla_tribunal:
            parameters['siglaTribunal'] = sigla_tribunal
        if orgao_id > 0:
            parameters['orgaoId'] = orgao_id
        if data_inicio:
            parameters['dataDisponibilizacaoInicio'] = data_inicio.strftime('%Y-%m-%d')
        if data_fim:
            parameters['dataDisponibilizacaoFim'] = data_fim.strftime('%Y-%m-%d')
        
        if parameters:
            return SearchRule(
                name=rule_name,
                rule_type=rule_type,
                operator=rule_operator if rule_type == RuleType.INCLUDE else RuleOperator.OR,
                enabled=rule_enabled,
                parameters=parameters
            )
        
        return None

def display_publication_card(pub: Dict, index: int):
    """Exibe uma publicação como card"""
    with st.container():
        st.markdown(f"""
        <div class="publication-card">
            <div class="publication-title">
                {pub.get('tipoComunicacao', 'N/A')} - {pub.get('siglaTribunal', 'N/A')}
            </div>
            <div class="publication-info">
                📅 <strong>Data:</strong> {pub.get('datadisponibilizacao', 'N/A')} | 
                🏛️ <strong>Órgão:</strong> {pub.get('nomeOrgao', 'N/A')}
            </div>
            <div class="publication-info">
                📋 <strong>Processo:</strong> {pub.get('numeroprocessocommascara', 'N/A')} | 
                📝 <strong>Classe:</strong> {pub.get('nomeClasse', 'N/A')}
            </div>
        """, unsafe_allow_html=True)
        
        # Texto da publicação
        texto = pub.get('texto', 'Texto não disponível')
        if len(texto) > 500:
            with st.expander("📄 Ver texto completo"):
                st.markdown(f'<div class="publication-text">{texto}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="publication-text">{texto}</div>', unsafe_allow_html=True)
        
        # Destinatários
        destinatarios = pub.get('destinatarios', [])
        if destinatarios:
            st.markdown("**👥 Destinatários:**")
            for dest in destinatarios:
                st.markdown(f"- {dest.get('nome', 'N/A')} ({dest.get('polo', 'N/A')})")
        
        # Advogados
        advogados = pub.get('destinatarioadvogados', [])
        if advogados:
            st.markdown("**⚖️ Advogados:**")
            for adv_info in advogados:
                adv = adv_info.get('advogado', {})
                st.markdown(f"""
                <div class="lawyer-info">
                    <strong>{adv.get('nome', 'N/A')}</strong><br>
                    OAB: {adv.get('numero_oab', 'N/A')}/{adv.get('uf_oab', 'N/A')}
                </div>
                """, unsafe_allow_html=True)
        
        # Link para o processo
        link = pub.get('link', '')
        if link:
            st.markdown(f"[🔗 Acessar processo]({link})")
        
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("---")

def display_rule_summary(rules: List[SearchRule]):
    """Exibe resumo das regras configuradas"""
    st.markdown("## 📋 Resumo das Regras")
    
    for i, rule in enumerate(rules):
        rule_class = "rule-include" if rule.rule_type == RuleType.INCLUDE else "rule-exclude"
        if not rule.enabled:
            rule_class += " rule-disabled"
        
        status = "✅ Ativa" if rule.enabled else "❌ Inativa"
        type_text = "🔍 Incluir" if rule.rule_type == RuleType.INCLUDE else "🚫 Excluir"
        operator_text = f"({rule.operator.value.upper()})" if rule.rule_type == RuleType.INCLUDE else ""
        
        params_text = []
        for key, value in rule.parameters.items():
            if key != '_rule_name':
                params_text.append(f"{key}: {value}")
        
        st.markdown(f"""
        <div class="rule-card {rule_class}">
            <strong>{rule.name}</strong> - {type_text} {operator_text} - {status}<br>
            <small>Parâmetros: {', '.join(params_text) if params_text else 'Nenhum'}</small>
        </div>
        """, unsafe_allow_html=True)

def main():
    st.title("⚖️ Automação de buscas pelo DJEN- CNJ")
    st.markdown("Sistema básico para validação dos parametros para busca de publicações do Diário de Justiça Eletrônico com regras personalizáveis")
    
    # Inicializa session state
    if 'rules' not in st.session_state:
        st.session_state.rules = []
    if 'template_loaded' not in st.session_state:
        st.session_state.template_loaded = False
    
    # Sidebar para configuração de regras
    with st.sidebar:
        st.header("🔧 Configuração de Regras")
        
        # Botões para gerenciar regras
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ Adicionar Regra"):
                st.session_state.rules.append(None)
                st.rerun()
        
        with col2:
            if st.button("🗑️ Limpar Regras"):
                st.session_state.rules = []
                st.session_state.template_loaded = False
                st.rerun()
        
        # Templates de regras
        st.markdown("### 📋 Templates de Regras")
        if st.button("📋 Carregar Template Padrão"):
            # Clear existing rules first
            st.session_state.rules = []
            
            # Create default rules with explicit RuleType objects
            default_rules = [
                SearchRule(
                    name="OAB Principal",
                    rule_type=RuleType.INCLUDE,
                    operator=RuleOperator.OR,
                    enabled=True,
                    parameters={'numeroOab': '8773', 'ufOab': 'ES', 'dataDisponibilizacaoInicio': '2025-07-08'}
                ),
                SearchRule(
                    name="Cliente Darwin",
                    rule_type=RuleType.INCLUDE,
                    operator=RuleOperator.OR,
                    enabled=True,
                    parameters={'nomeParte': 'Darwin', 'dataDisponibilizacaoInicio': '2025-07-08'}
                ),
                SearchRule(
                    name="Cliente Multivix",
                    rule_type=RuleType.INCLUDE,
                    operator=RuleOperator.OR,
                    enabled=True,
                    parameters={'nomeParte': 'Multivix', 'dataDisponibilizacaoInicio': '2025-07-08'}
                ), 
                SearchRule(
                    name="Cliente Sinales",
                    rule_type=RuleType.INCLUDE,
                    operator=RuleOperator.OR,
                    enabled=True,
                    parameters={'nomeParte': 'Sinales', 'dataDisponibilizacaoInicio': '2025-07-08'}
                ), 
                SearchRule(
                    name="Cliente Ajudes",
                    rule_type=RuleType.INCLUDE,
                    operator=RuleOperator.OR,
                    enabled=True,
                    parameters={'nomeParte': 'Ajudes', 'dataDisponibilizacaoInicio': '2025-07-08'}
                ), 
                SearchRule(
                    name="Cliente Claretiano",
                    rule_type=RuleType.INCLUDE,
                    operator=RuleOperator.OR,
                    enabled=True,
                    parameters={'nomeParte': 'Claretiano', 'dataDisponibilizacaoInicio': '2025-07-08'}
                ), 
                SearchRule(
                    name="Exclusão Itiel",
                    rule_type=RuleType.EXCLUDE,
                    operator=RuleOperator.OR,
                    enabled=True,
                    parameters={'numeroOab': '14072', 'ufOab': 'ES','nomeParte': 'Sinales', 'dataDisponibilizacaoInicio': '2025-07-08'}
                )
            ]
            
            st.session_state.rules = default_rules
            st.session_state.template_loaded = True
            st.success("Template carregado com sucesso!")
            st.rerun()
    
    # Área principal - Configuração de regras
    st.markdown("## ⚙️ Configuração de Regras")
    
    # Formulários de regras
    configured_rules = []
    for i in range(len(st.session_state.rules)):
        existing_rule = st.session_state.rules[i]
        rule = create_rule_form(i, existing_rule)
        if rule:
            configured_rules.append(rule)
    
    # Atualiza regras no session state apenas se não for template
    if not st.session_state.template_loaded:
        st.session_state.rules = configured_rules
    else:
        # Reset template flag after first render
        st.session_state.template_loaded = False
    
    # Exibe resumo das regras
    if configured_rules:
        display_rule_summary(configured_rules)
        
        # Botão de busca
        if st.button("🔍 Executar Busca", type="primary"):
            searcher = EnhancedDJESearcher()
            
            # Progress bar e status
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def update_progress(message):
                status_text.markdown(f'<div class="search-progress">🔍 {message}</div>', unsafe_allow_html=True)
            
            try:
                # Executa as regras
                publications = searcher.execute_rules(configured_rules, update_progress)
                
                progress_bar.progress(100)
                status_text.success(f"✅ Busca concluída! {len(publications)} publicações encontradas.")
                
                # Armazena os resultados na sessão
                st.session_state.publications = publications
                st.session_state.search_completed = True
                
            except Exception as e:
                st.error(f"Erro durante a busca: {str(e)}")
                return
    
    # Exibe os resultados se existirem
    if hasattr(st.session_state, 'publications') and st.session_state.publications:
        publications = st.session_state.publications
        
        # Filtros
        st.markdown("## 🔍 Filtros dos Resultados")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            tribunais = sorted(list(set([pub.get('siglaTribunal', 'N/A') for pub in publications])))
            tribunal_filter = st.selectbox("Tribunal", ["Todos"] + tribunais)
        
        with col2:
            tipos = sorted(list(set([pub.get('tipoComunicacao', 'N/A') for pub in publications])))
            tipo_filter = st.selectbox("Tipo de Comunicação", ["Todos"] + tipos)
        
        with col3:
            classes = sorted(list(set([pub.get('nomeClasse', 'N/A') for pub in publications])))
            classe_filter = st.selectbox("Classe Processual", ["Todos"] + classes)
        
        # Aplicar filtros
        filtered_publications = publications
        if tribunal_filter != "Todos":
            filtered_publications = [pub for pub in filtered_publications if pub.get('siglaTribunal') == tribunal_filter]
        if tipo_filter != "Todos":
            filtered_publications = [pub for pub in filtered_publications if pub.get('tipoComunicacao') == tipo_filter]
        if classe_filter != "Todos":
            filtered_publications = [pub for pub in filtered_publications if pub.get('nomeClasse') == classe_filter]
        
        # Paginação
        st.markdown("## 📋 Resultados")
        items_per_page = 10
        total_items = len(filtered_publications)
        total_pages = math.ceil(total_items / items_per_page)
        
        if total_pages > 1:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                page = st.selectbox("Página", range(1, total_pages + 1))
        else:
            page = 1
        
        # Exibe informações da paginação
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_items = filtered_publications[start_idx:end_idx]
        
        st.info(f"Mostrando {len(current_items)} de {total_items} publicações (Página {page} de {total_pages})")
        
        # Exibe as publicações
        for i, pub in enumerate(current_items):
            display_publication_card(pub, start_idx + i)
        
        # Exportar resultados
        st.markdown("## 📊 Exportar Resultados")
        if st.button("📋 Exportar como JSON"):
            json_data = json.dumps(filtered_publications, indent=2, ensure_ascii=False)
            st.download_button(
                label="💾 Baixar JSON",
                data=json_data,
                file_name=f"dje_search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
    
    elif hasattr(st.session_state, 'search_completed') and st.session_state.search_completed:
        st.info("Nenhuma publicação encontrada com os critérios especificados.")
    
    else:
        st.info("Configure as regras acima e clique em 'Executar Busca' para começar.")
        
        # Ajuda
        with st.expander("📖 Como usar o sistema de regras"):
            st.markdown("""
            ### 🔍 Tipos de Regras
            
            **Regras de Inclusão (🔍):**
            - Buscam publicações que atendem aos critérios especificados
            - Operador OU: Une resultados de múltiplas regras
            - Operador E: Mantém apenas resultados que aparecem em todas as regras
            
            **Regras de Exclusão (🚫):**
            - Removem publicações dos resultados finais
            - Úteis para filtrar resultados indesejados
            
            ### 📋 Parâmetros Disponíveis
            
            - **numeroOab/ufOab**: Número e UF da OAB do advogado
            - **nomeAdvogado**: Nome do advogado
            - **nomeParte**: Nome da parte no processo
            - **numeroProcesso**: Número do processo
            - **numeroComunicacao**: Número específico da comunicação
            - **siglaTribunal**: Sigla do tribunal (ex: TJES, TJMG)
            - **orgaoId**: ID interno do órgão
            - **dataDisponibilizacaoInicio/Fim**: Período de disponibilização
            
            ### 💡 Exemplos de Uso
            
            1. **Buscar por OAB específica**: numeroOab + ufOab
            2. **Buscar cliente específico**: nomeParte + dataInicio
            3. **Excluir processos específicos**: numeroProcesso (como regra de exclusão)
            4. **Filtrar por tribunal**: siglaTribunal
            """)

if __name__ == "__main__":
    main()

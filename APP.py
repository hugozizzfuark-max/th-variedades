import streamlit as st
import pandas as pd
import unicodedata
from datetime import datetime
import os

# =========================================================
# CONFIGURAÇÃO DA PÁGINA STREAMLIT
# =========================================================
st.set_page_config(
    page_title="TH Variedades - Gestão & Estoque",
    page_icon="🛍️",
    layout="wide"
)

# Caminhos dos arquivos de dados locais/repositório
ARQUIVO_ESTOQUE = "estoque.csv"
ARQUIVO_VENDAS = "vendas.csv"

# =========================================================
# FUNÇÕES AUXILIARES DE DADOS
# =========================================================
def normalizar_texto(texto):
    """Remove acentos, espaços extras e converte para minúsculas"""
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(texto))
        if unicodedata.category(c) != 'Mn'
    ).lower().strip()

def carregar_estoque():
    if os.path.exists(ARQUIVO_ESTOQUE):
        return pd.read_csv(ARQUIVO_ESTOQUE)
    else:
        return pd.DataFrame(columns=[
            'sku', 'nome_produto', 'quantidade_estoque', 
            'preco_custo_unitario', 'frete_unitario', 'custo_total_unitario', 
            'preco_venda_unitario', 'ultimo_pedido_id'
        ])

def carregar_vendas():
    if os.path.exists(ARQUIVO_VENDAS):
        return pd.read_csv(ARQUIVO_VENDAS)
    else:
        return pd.DataFrame(columns=[
            'id_venda', 'sku', 'nome_produto', 'quantidade_vendida', 
            'preco_venda_praticado', 'custo_unitario', 'lucro_total_venda', 'data_hora'
        ])

def salvar_dados(df_estoque, df_vendas):
    df_estoque.to_csv(ARQUIVO_ESTOQUE, index=False)
    df_vendas.to_csv(ARQUIVO_VENDAS, index=False)

def processar_csv_upload(uploaded_file, df_estoque):
    try:
        try:
            df_novo = pd.read_csv(uploaded_file, sep=',')
            if len(df_novo.columns) < 2:
                uploaded_file.seek(0)
                df_novo = pd.read_csv(uploaded_file, sep=';')
        except:
            uploaded_file.seek(0)
            df_novo = pd.read_csv(uploaded_file, sep=';')

        df_novo.columns = [normalizar_texto(col) for col in df_novo.columns]
        
        # Validar colunas
        colunas_necessarias = ['nome_produto', 'quantidade', 'preco_custo_unitario']
        for col in colunas_necessarias:
            if col not in df_novo.columns:
                st.error(f"Coluna obrigatória '{col}' não foi encontrada no arquivo CSV.")
                return df_estoque, False

        # Tratamento numérico
        df_novo['quantidade'] = pd.to_numeric(df_novo['quantidade'], errors='coerce').fillna(0).astype(int)
        df_novo['preco_custo_unitario'] = pd.to_numeric(
            df_novo['preco_custo_unitario'].astype(str).str.replace('R$', '', regex=False).str.replace(',', '.').str.strip(),
            errors='coerce'
        ).fillna(0.0)

        frete_total = 0.0
        if 'frete_total' in df_novo.columns:
            frete_val = pd.to_numeric(
                df_novo['frete_total'].astype(str).str.replace('R$', '', regex=False).str.replace(',', '.').str.strip(),
                errors='coerce'
            ).max()
            if pd.notna(frete_val):
                frete_total = float(frete_val)

        df_novo['valor_total_item'] = df_novo['quantidade'] * df_novo['preco_custo_unitario']

        # Rateio do frete
        subtotal = df_novo['valor_total_item'].sum()
        if subtotal > 0 and frete_total > 0:
            df_novo['peso_valor'] = df_novo['valor_total_item'] / subtotal
            df_novo['frete_unitario'] = (df_novo['peso_valor'] * frete_total) / df_novo['quantidade']
        else:
            df_novo['frete_unitario'] = 0.0

        df_novo['custo_total_unitario'] = df_novo['preco_custo_unitario'] + df_novo['frete_unitario']

        # Atualizar tabela de estoque
        id_pedido = f"PED-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        for _, row in df_novo.iterrows():
            nome = str(row['nome_produto']).strip()
            qtd = row['quantidade']
            custo_unit = row['preco_custo_unitario']
            frete_unit = row['frete_unitario']
            custo_tot_unit = row['custo_total_unitario']

            match_index = df_estoque[
                df_estoque['nome_produto'].astype(str).str.strip().str.lower() == nome.lower()
            ].index

            if len(match_index) > 0:
                idx = match_index[0]
                qtd_antiga = df_estoque.at[idx, 'quantidade_estoque']
                custo_tot_antigo = df_estoque.at[idx, 'custo_total_unitario']

                qtd_nova_total = qtd_antiga + qtd
                novo_custo_medio = (
                    ((qtd_antiga * custo_tot_antigo) + (qtd * custo_tot_unit)) / qtd_nova_total
                    if qtd_nova_total > 0 else custo_tot_unit
                )

                df_estoque.at[idx, 'quantidade_estoque'] = qtd_nova_total
                df_estoque.at[idx, 'custo_total_unitario'] = round(novo_custo_medio, 2)
                df_estoque.at[idx, 'ultimo_pedido_id'] = id_pedido
            else:
                novo_sku = f"TH-{len(df_estoque) + 1:03d}"
                novo_item = {
                    'sku': novo_sku,
                    'nome_produto': nome,
                    'quantidade_estoque': qtd,
                    'preco_custo_unitario': round(custo_unit, 2),
                    'frete_unitario': round(frete_unit, 2),
                    'custo_total_unitario': round(custo_tot_unit, 2),
                    'preco_venda_unitario': 0.0,
                    'ultimo_pedido_id': id_pedido
                }
                df_estoque = pd.concat([df_estoque, pd.DataFrame([novo_item])], ignore_index=True)

        return df_estoque, True
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")
        return df_estoque, False

# =========================================================
# CARREGAR ESTADO DOS DADOS
# =========================================================
df_estoque = carregar_estoque()
df_vendas = carregar_vendas()

# =========================================================
# INTERFACE GRÁFICA (SIDEBAR E NAVEGAÇÃO)
# =========================================================
st.sidebar.title("🛍️ TH Variedades")
st.sidebar.markdown("---")
menu = st.sidebar.radio("Navegação", ["📊 Dashboard & KPIs", "📦 Estoque & Preços", "🛒 Registrar Venda", "📥 Importar Pedido (CSV)"])

# ---------------------------------------------------------
# ABA 1: DASHBOARD & KPIS
# ---------------------------------------------------------
if menu == "📊 Dashboard & KPIs":
    st.title("📊 Painel Geral de Vendas e Previsões")
    
    # Cálculos Globais
    faturamento_real = (df_vendas['quantidade_vendida'] * df_vendas['preco_venda_praticado']).sum() if not df_vendas.empty else 0.0
    lucro_real = df_vendas['lucro_total_venda'].sum() if not df_vendas.empty else 0.0
    
    prev_faturamento = (df_estoque['quantidade_estoque'] * df_estoque['preco_venda_unitario']).sum()
    prev_lucro = (df_estoque['quantidade_estoque'] * (df_estoque['preco_venda_unitario'] - df_estoque['custo_total_unitario'])).sum()
    
    # Cartões Indicadores
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Faturamento Realizado", f"R$ {faturamento_real:.2f}")
    col2.metric("Lucro Realizado", f"R$ {lucro_real:.2f}")
    col3.metric("Prev. Faturamento (Estoque)", f"R$ {prev_faturamento:.2f}")
    col4.metric("Prev. Lucro Total (Estoque)", f"R$ {prev_lucro:.2f}")

    st.markdown("---")
    st.subheader("📋 Histórico Recente de Vendas")
    if not df_vendas.empty:
        st.dataframe(df_vendas.sort_values(by="data_hora", ascending=False), use_container_width=True)
    else:
        st.info("Nenhuma venda registrada até o momento.")

# ---------------------------------------------------------
# ABA 2: ESTOQUE E PREÇOS
# ---------------------------------------------------------
elif menu == "📦 Estoque & Preços":
    st.title("📦 Gerenciamento de Estoque e Margens")
    
    if not df_estoque.empty:
        st.markdown("Edite o **Preço de Venda Unitário** diretamente na tabela abaixo:")
        
        # Tabela editável
        df_editavel = st.data_editor(
            df_estoque,
            column_config={
                "sku": st.column_config.TextColumn("SKU", disabled=True),
                "nome_produto": st.column_config.TextColumn("Produto", disabled=True),
                "quantidade_estoque": st.column_config.NumberColumn("Estoque Atual", disabled=True),
                "preco_custo_unitario": st.column_config.NumberColumn("Custo Nota (R$)", disabled=True, format="R$ %.2f"),
                "frete_unitario": st.column_config.NumberColumn("Frete Unit. (R$)", disabled=True, format="R$ %.2f"),
                "custo_total_unitario": st.column_config.NumberColumn("Custo Total (R$)", disabled=True, format="R$ %.2f"),
                "preco_venda_unitario": st.column_config.NumberColumn("Preço de Venda (R$)", min_value=0.0, format="R$ %.2f"),
                "ultimo_pedido_id": st.column_config.TextColumn("Lote Pedido", disabled=True)
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("💾 Salvar Alterações nos Preços"):
            salvar_dados(df_editavel, df_vendas)
            st.success("Preços e estoque atualizados com sucesso!")
            st.rerun()
    else:
        st.info("O estoque está vazio. Importe um pedido em CSV para começar.")

# ---------------------------------------------------------
# ABA 3: REGISTRAR VENDA (PDV)
# ---------------------------------------------------------
elif menu == "🛒 Registrar Venda":
    st.title("🛒 Baixa Rápida de Venda")
    
    if not df_estoque.empty:
        # Filtrar apenas produtos que possuem estoque disponível
        df_disponivel = df_estoque[df_estoque['quantidade_estoque'] > 0]
        
        if not df_disponivel.empty:
            lista_produtos = df_disponivel.apply(lambda x: f"{x['sku']} - {x['nome_produto']} (Estoque: {x['quantidade_estoque']})", axis=1)
            
            produto_selecionado = st.selectbox("Selecione o Produto:", lista_produtos)
            sku_selecionado = produto_selecionado.split(" - ")[0]
            
            # Buscar dados do produto selecionado
            item = df_estoque[df_estoque['sku'] == sku_selecionado].iloc[0]
            
            col_a, col_b = st.columns(2)
            with col_a:
                qtd_venda = st.number_input("Quantidade Vendida:", min_value=1, max_value=int(item['quantidade_estoque']), value=1)
            with col_b:
                preco_venda_input = st.number_input("Preço Praticado por Unidade (R$):", min_value=0.0, value=float(item['preco_venda_unitario']))

            lucro_estimado = (preco_venda_input - item['custo_total_unitario']) * qtd_venda
            st.info(f"Lucro total desta venda: **R$ {lucro_estimado:.2f}**")

            if st.button("✅ Confirmar e Dar Baixa"):
                idx = df_estoque[df_estoque['sku'] == sku_selecionado].index[0]
                
                # Atualizar Estoque
                df_estoque.at[idx, 'quantidade_estoque'] -= qtd_venda
                
                # Registrar Venda
                nova_venda = {
                    'id_venda': f"VENDA-{len(df_vendas)+1:04d}",
                    'sku': sku_selecionado,
                    'nome_produto': item['nome_produto'],
                    'quantidade_vendida': qtd_venda,
                    'preco_venda_praticado': preco_venda_input,
                    'custo_unitario': item['custo_total_unitario'],
                    'lucro_total_venda': round(lucro_estimado, 2),
                    'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                df_vendas = pd.concat([df_vendas, pd.DataFrame([nova_venda])], ignore_index=True)
                
                salvar_dados(df_estoque, df_vendas)
                st.success(f"Venda de {qtd_venda}x '{item['nome_produto']}' registrada com sucesso!")
                st.rerun()
        else:
            st.warning("Todos os produtos cadastrados estão sem estoque disponível.")
    else:
        st.info("Nenhum produto cadastrado no estoque.")

# ---------------------------------------------------------
# ABA 4: IMPORTAR PEDIDO (CSV)
# ---------------------------------------------------------
elif menu == "📥 Importar Pedido (CSV)":
    st.title("📥 Importar Novo Pedido de Fornecedor")
    st.markdown("Faça o upload do arquivo `.csv` para adicionar novos produtos ou incrementar o estoque de produtos existentes.")
    
    arquivo_upload = st.file_uploader("Escolha o arquivo CSV do Pedido", type=["csv"])
    
    if arquivo_upload is not None:
        if st.button("🚀 Processar e Adicionar ao Estoque"):
            df_estoque, sucesso = processar_csv_upload(arquivo_upload, df_estoque)
            if sucesso:
                salvar_dados(df_estoque, df_vendas)
                st.success("Pedido importado e estoque atualizado com sucesso!")
                st.rerun()
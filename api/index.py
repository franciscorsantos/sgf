from flask import Flask, render_template, request, redirect, url_for, send_file
from datetime import datetime
import os
import io
import openpyxl
try:
    import psycopg2
except ImportError:
    psycopg2 = None
import sqlite3
import logging


app = Flask(__name__, template_folder='../templates', static_folder='../static')

def get_db_connection():
    if 'POSTGRES_URL' in os.environ:
        if psycopg2 is None:
            raise ImportError("A biblioteca 'psycopg2' é necessária para conexão com PostgreSQL, mas não está instalada.")
        return psycopg2.connect(os.environ['POSTGRES_URL'])
    return sqlite3.connect('database.db')

def init_db():
    """Cria a tabela de transações se ela não existir."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Ajusta a sintaxe SQL dependendo do banco (Postgres vs SQLite)
        if 'POSTGRES_URL' in os.environ:
            id_col = "SERIAL PRIMARY KEY"
        else:
            id_col = "INTEGER PRIMARY KEY AUTOINCREMENT"

        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS transacoes (
                id {id_col},
                data VARCHAR(20),
                tipo VARCHAR(20),
                categoria VARCHAR(100),
                valor REAL,
                descricao TEXT
            );
        """)

        # Cria tabela de Contas a Pagar
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS contas_a_pagar (
                id {id_col},
                data_vencimento VARCHAR(20),
                categoria VARCHAR(100),
                valor REAL,
                descricao TEXT,
                status VARCHAR(20)
            );
        """)
        conn.commit()
        cur.close()
    except Exception as e:
        logging.error(f"Aviso: Não foi possível conectar ao banco na inicialização: {e}")
    finally:
        if conn:
            conn.close()

# Inicialização: Garante que a tabela exista ao iniciar
init_db()

# 2. Espelho 'Planos de Contas' (Opções de Menu)
CATEGORIAS = {
    'entrada': [
        '1. Receitas',
        '1.1 Fretes / Transportes',
        '1.2 Redespacho',
        '1.3 Armazenagem',
        '1.4 Venda de Ativos'
    ],
    'saida': [
        '2. Custos Variáveis (Veículo)',
        '2.1 Combustível',
        '2.2 Manutenção Preventiva',
        '2.3 Manutenção Corretiva',
        '2.4 Pneus',
        '2.5 Pedágio / Estacionamento',
        '2.6 Sinistro / Franquia ',
        '2.7 Diárias / Alimentação Motorista',
        '2.8 Custo com Agregados / Terceiros',
        '3. Custos Fixos (Operacional)',
        '3.1 Folha de Pagamento',
        '3.2 Encargos sobre a Folha de Pagamento',
        '3.3 Seguros',
        '3.4 Monitoramento / Rastreamento',
        '3.5 Documentação Frota',
        '3.6 Aluguel de Frota',
        '4. Despesas Administrativas',
        '4.1 Energia Elétrica',
        '4.2 Água e Esgoto',
        '4.3 Internet',
        '4.4 Telefonia Fixa / Móvel',
        '4.5 Softwares e Sistemas',
        '4.6 Contabilidade',
        '4.7 Tarifas Bancárias',
        '4.8 Pro-Labore',
        '4.9 Encargos sobre o Pro-Labore',
        '4.10 Material de Escritorio',
        '4.11 Material de Limpeza',
        '4.12 Brindes / Patricionios',
        '4.13 Outras Despesas Administrativas',
        '4.14 Salários Administrativos',
        '5. Impostos',
        '5.1 Simples Nacional',
        '6. Investimentos',
        '6.1 Pgto. Emprestimos / Financiamentos',
        '6.2 Reserva de Emergência',
    ]
}

@app.route('/', methods=['GET', 'POST'])
def home():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        # Captura dados do Formulário
        sql = 'INSERT INTO transacoes (data, tipo, categoria, valor, descricao) VALUES (%s, %s, %s, %s, %s)'
        
        # Usa placeholder (?) para SQLite se não estiver no ambiente Postgres
        if 'POSTGRES_URL' not in os.environ:
            sql = sql.replace('%s', '?')

        cur.execute(sql,
                    (request.form.get('data'),
                     request.form.get('tipo'),
                     request.form.get('categoria'),
                     float(request.form.get('valor')),
                     request.form.get('descricao')))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('home'))

    # Busca transações do banco
    cur.execute('SELECT * FROM transacoes ORDER BY id DESC')
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Converte para lista de dicionários para manter compatibilidade com o template
    transacoes = [{'id': r[0], 'data': r[1], 'tipo': r[2], 'categoria': r[3], 'valor': r[4], 'descricao': r[5]} for r in rows]

    # Cálculos para o Dashboard
    total_entradas = sum(t['valor']
                        for t in transacoes if t['tipo'] == 'entrada')
    total_saidas = sum(t['valor']
                    for t in transacoes if t['tipo'] == 'saida')
    saldo = total_entradas - total_saidas

    return render_template('index.html',
                            transacoes=transacoes,
                            entrada=total_entradas,
                            saidas=total_saidas,
                            saldo=saldo,
                            categorias=CATEGORIAS,
                            hoje=datetime.today().strftime('%d-%m-%Y')) # Entreda a data atual formatada

@app.route('/limpar-banco')
def limpar_banco():
    """Rota utilitária para limpar o banco de dados (CUIDADO: Apaga tudo!)"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS transacoes")
    cur.execute("DROP TABLE IF EXISTS contas_a_pagar")
    conn.commit()
    cur.close()
    conn.close()
    
    # Recria a tabela vazia
    init_db()
    
    return redirect(url_for('home'))

def get_filtered_rows(tipo, mes):
    conn = get_db_connection()
    cur = conn.cursor()

    query = "SELECT * FROM transacoes WHERE 1=1"
    params = []

    if tipo and tipo in ['entrada', 'saida']:
        # Adiciona filtro de tipo
        query += " AND tipo = %s" if 'POSTGRES_URL' in os.environ else " AND tipo = ?"
        params.append(tipo)

    if mes:
        # Converte YYYY-MM para MM-YYYY para buscar na string de data (DD-MM-YYYY)
        ano, mes_val = mes.split('-')
        mes_formatado = f"{mes_val}-{ano}"
        
        query += " AND data LIKE %s" if 'POSTGRES_URL' in os.environ else " AND data LIKE ?"
        params.append(f"%{mes_formatado}")

    query += " ORDER BY id DESC"

    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

@app.route('/relatorios')
def relatorios():
    # Parâmetros de Filtro (GET)
    tipo = request.args.get('tipo')
    mes = request.args.get('mes') # Vem no formato YYYY-MM do input type="month"

    rows = get_filtered_rows(tipo, mes)

    transacoes_filtradas = [{'id': r[0], 'data': r[1], 'tipo': r[2], 'categoria': r[3], 'valor': r[4], 'descricao': r[5]} for r in rows]

    # Prepara dados para o gráfico (Agrupa despesas por categoria)
    gastos_por_categoria = {}
    for t in transacoes_filtradas:
        if t['tipo'] == 'saida':
            cat = t['categoria']
            gastos_por_categoria[cat] = gastos_por_categoria.get(cat, 0) + t['valor']

    # Prepara dados para o gráfico de barras (Entradas vs Saídas por Mês)
    historico_meses = {}
    for t in transacoes_filtradas:
        try:
            # Converte string DD-MM-YYYY para objeto data e extrai MM-YYYY
            data_obj = datetime.strptime(t['data'], '%d-%m-%Y')
            chave = data_obj.strftime('%m-%Y')
            
            if chave not in historico_meses:
                historico_meses[chave] = {'entrada': 0, 'saida': 0}
            
            if t['tipo'] in ['entrada', 'saida']:
                historico_meses[chave][t['tipo']] += t['valor']
        except (ValueError, TypeError):
            continue # Ignora datas inválidas

    # Ordena os meses cronologicamente
    meses_ordenados = sorted(historico_meses.keys(), key=lambda x: datetime.strptime(x, '%m-%Y'))
    
    barras_labels = meses_ordenados
    barras_entradas = [historico_meses[m]['entrada'] for m in meses_ordenados]
    barras_saidas = [historico_meses[m]['saida'] for m in meses_ordenados]

    total_entradas = sum(t['valor'] for t in transacoes_filtradas if t['tipo'] == 'entrada')
    total_saidas = sum(t['valor'] for t in transacoes_filtradas if t['tipo'] == 'saida')
    saldo = total_entradas - total_saidas

    return render_template('relatorios.html',
                           transacoes=transacoes_filtradas,
                           entrada=total_entradas,
                           saidas=total_saidas,
                           saldo=saldo,
                           gastos_por_categoria=gastos_por_categoria,
                           barras_labels=barras_labels,
                           barras_entradas=barras_entradas,
                           barras_saidas=barras_saidas,
                           filtro_tipo=tipo,
                           filtro_mes=mes)

@app.route('/exportar')
def exportar():
    tipo = request.args.get('tipo')
    mes = request.args.get('mes')
    
    rows = get_filtered_rows(tipo, mes)
    
    # Cria o arquivo Excel em memória
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Relatório"
    
    # Cabeçalhos
    ws.append(["ID", "Data", "Tipo", "Categoria", "Valor", "Descrição"])
    
    for row in rows:
        ws.append(row)
        
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    filename = f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/contas-a-pagar', methods=['GET', 'POST'])
def contas_a_pagar():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        sql = 'INSERT INTO contas_a_pagar (data_vencimento, categoria, valor, descricao, status) VALUES (%s, %s, %s, %s, %s)'
        if 'POSTGRES_URL' not in os.environ:
            sql = sql.replace('%s', '?')
        
        cur.execute(sql, (
            request.form.get('data_vencimento'),
            request.form.get('categoria'),
            float(request.form.get('valor')),
            request.form.get('descricao'),
            'pendente'
        ))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('contas_a_pagar'))

    # Lista apenas as pendentes
    cur.execute("SELECT * FROM contas_a_pagar WHERE status = 'pendente' ORDER BY data_vencimento ASC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    contas = [{'id': r[0], 'data_vencimento': r[1], 'categoria': r[2], 'valor': r[3], 'descricao': r[4], 'status': r[5]} for r in rows]
    
    return render_template('contas_a_pagar.html', contas=contas, categorias=CATEGORIAS)

@app.route('/confirmar-pagamento/<int:id>')
def confirmar_pagamento(id):
    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Busca a conta a pagar
    cur.execute("SELECT * FROM contas_a_pagar WHERE id = %s" if 'POSTGRES_URL' in os.environ else "SELECT * FROM contas_a_pagar WHERE id = ?", (id,))
    conta = cur.fetchone()

    if conta:
        # 2. Insere na tabela de transações (Fluxo de Caixa Real) como SAÍDA
        sql_transacao = 'INSERT INTO transacoes (data, tipo, categoria, valor, descricao) VALUES (%s, %s, %s, %s, %s)'
        if 'POSTGRES_URL' not in os.environ:
            sql_transacao = sql_transacao.replace('%s', '?')
        
        # Usa a data de hoje como data do pagamento
        data_hoje = datetime.today().strftime('%d-%m-%Y')
        # conta[2] é categoria, conta[3] é valor, conta[4] é descricao
        cur.execute(sql_transacao, (data_hoje, 'saida', conta[2], conta[3], f"{conta[4]} (Pgto Conta)"))

        # 3. Atualiza o status na tabela de contas a pagar para 'pago'
        sql_update = "UPDATE contas_a_pagar SET status = 'pago' WHERE id = %s" if 'POSTGRES_URL' in os.environ else "UPDATE contas_a_pagar SET status = 'pago' WHERE id = ?"
        cur.execute(sql_update, (id,))
        
        conn.commit()

    cur.close()
    conn.close()
    return redirect(url_for('contas_a_pagar'))

def get_filtered_contas(status, mes):
    conn = get_db_connection()
    cur = conn.cursor()

    query = "SELECT * FROM contas_a_pagar WHERE 1=1"
    params = []

    if status and status in ['pendente', 'pago']:
        query += " AND status = %s" if 'POSTGRES_URL' in os.environ else " AND status = ?"
        params.append(status)

    if mes:
        # Converte YYYY-MM para MM-YYYY para buscar na string de data (DD-MM-YYYY)
        ano, mes_val = mes.split('-')
        mes_formatado = f"{mes_val}-{ano}"
        
        query += " AND data_vencimento LIKE %s" if 'POSTGRES_URL' in os.environ else " AND data_vencimento LIKE ?"
        params.append(f"%{mes_formatado}")

    query += " ORDER BY data_vencimento ASC"

    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

@app.route('/relatorios-contas')
def relatorios_contas():
    status = request.args.get('status')
    mes = request.args.get('mes')

    rows = get_filtered_contas(status, mes)
    
    contas = [{'id': r[0], 'data_vencimento': r[1], 'categoria': r[2], 'valor': r[3], 'descricao': r[4], 'status': r[5]} for r in rows]

    total_pendente = sum(c['valor'] for c in contas if c['status'] == 'pendente')
    total_pago = sum(c['valor'] for c in contas if c['status'] == 'pago')
    
    return render_template('relatorios_contas.html',
                           contas=contas,
                           total_pendente=total_pendente,
                           total_pago=total_pago,
                           filtro_status=status,
                           filtro_mes=mes)

@app.route('/exportar-contas')
def exportar_contas():
    status = request.args.get('status')
    mes = request.args.get('mes')
    
    rows = get_filtered_contas(status, mes)
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Relatório Contas a Pagar"
    
    ws.append(["ID", "Vencimento", "Categoria", "Valor", "Descrição", "Status"])
    
    for row in rows:
        ws.append(row)
        
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    filename = f"relatorio_contas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/deletar-transacao/<int:id>')
def deletar_transacao(id):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "DELETE FROM transacoes WHERE id = %s" if 'POSTGRES_URL' in os.environ else "DELETE FROM transacoes WHERE id = ?"
    cur.execute(sql, (id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('home'))

@app.route('/deletar-conta/<int:id>')
def deletar_conta(id):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "DELETE FROM contas_a_pagar WHERE id = %s" if 'POSTGRES_URL' in os.environ else "DELETE FROM contas_a_pagar WHERE id = ?"
    cur.execute(sql, (id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('contas_a_pagar'))

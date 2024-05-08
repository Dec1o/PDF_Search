from tkinter import filedialog, messagebox, scrolledtext
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, UnidentifiedImageError
import tkinter as tk
import configparser
import pytesseract
import threading
import PyPDF2
import fitz
import os
import io

# Variáveis globais para armazenar os caminhos definidos pelo usuário
tesseract_path = ''
root_directory = ''
config_file = 'config.ini'

# Configurações
config = configparser.ConfigParser()

# Carrega configurações do arquivo .ini
def carregar_configuracoes():
    global tesseract_path, root_directory
    if os.path.exists(config_file):
        config.read(config_file)
        tesseract_path = config.get('paths', 'tesseract_path', fallback='')
        root_directory = config.get('paths', 'root_directory', fallback='')
        entrada_tesseract.insert(0, tesseract_path)
        entrada_root_directory.insert(0, root_directory)

# Salva configurações no arquivo .ini
def salvar_configuracoes():
    config['paths'] = {
        'tesseract_path': tesseract_path,
        'root_directory': root_directory
    }
    with open(config_file, 'w') as configfile:
        config.write(configfile)

# Seleciona o caminho do executável do Tesseract
def selecionar_tesseract_path():
    global tesseract_path
    tesseract_path = filedialog.askopenfilename(title="Selecione o executável do Tesseract", filetypes=[("Executável", "*.exe")])
    entrada_tesseract.delete(0, tk.END)
    entrada_tesseract.insert(0, tesseract_path)
    salvar_configuracoes()  # Salva as configurações assim que o usuário define o caminho

# Seleciona o diretório raiz para pesquisar PDFs
def selecionar_root_directory():
    global root_directory
    root_directory = filedialog.askdirectory(title="Selecione o diretório raiz para pesquisar PDFs")
    entrada_root_directory.delete(0, tk.END)
    entrada_root_directory.insert(0, root_directory)
    salvar_configuracoes()  # Salva as configurações assim que o usuário define o caminho

# Confirma as configurações
def confirmar_configuracoes():
    if not tesseract_path or not root_directory:
        messagebox.showerror("Erro", "Ambos os caminhos devem ser definidos.")
        return
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
    frame_configuracao.pack_forget()
    frame_pdf_search.pack()

# Pré-processamento de imagem
def preprocessamento_imagem(imagem):
    imagem_cinza = imagem.convert('L')
    limiar = 127
    imagem_binaria = imagem_cinza.point(lambda p: p > limiar and 255)
    return imagem_binaria

# Função para ler PDFs usando OCR
def ler_pdf_com_ocr(caminho_pdf):
    texto = ""
    documento = fitz.open(caminho_pdf)
    for pagina_num in range(documento.page_count):
        pagina = documento.load_page(pagina_num)
        imagens = pagina.get_images(full=True)
        for imagem_info in imagens:
            xref = imagem_info[0]
            base_imagem = documento.extract_image(xref)
            imagem_bytes = base_imagem.get('image')
            if not imagem_bytes:
                print(f"Aviso: Os bytes da imagem na página {pagina_num + 1} do PDF {caminho_pdf} estão vazios.")
                continue
            try:
                imagem_io = io.BytesIO(imagem_bytes)
                imagem = Image.open(imagem_io)
            except UnidentifiedImageError:
                print(f"Aviso: A imagem na página {pagina_num + 1} do PDF {caminho_pdf} não pôde ser identificada.")
                continue
            imagem_preprocessada = preprocessamento_imagem(imagem)
            texto += pytesseract.image_to_string(imagem_preprocessada)
    documento.close()
    return texto

# Função para ler PDFs usando PyPDF2
def ler_pdf_pypdf2(caminho_pdf):
    texto = ""
    with open(caminho_pdf, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        num_paginas = len(reader.pages)
        for pagina_num in range(num_paginas):
            pagina = reader.pages[pagina_num]
            texto += pagina.extract_text()
    return texto

# Modificação da função encontrar_nomes_pdfs_com_palavra_chave
def encontrar_nomes_pdfs_com_palavra_chave(diretorio, palavra_chave):
    nomes_pdfs_com_palavra_chave_ocr = []
    nomes_pdfs_com_palavra_chave_pypdf2 = []
    
    def processar_arquivo(arquivo, caminho_pdf):
        # Ler PDF com OCR
        texto_ocr = ler_pdf_com_ocr(caminho_pdf)
        if palavra_chave.lower() in texto_ocr.lower():
            nomes_pdfs_com_palavra_chave_ocr.append((arquivo, caminho_pdf))
        # Ler PDF com PyPDF2
        texto_pypdf2 = ler_pdf_pypdf2(caminho_pdf)
        if palavra_chave.lower() in texto_pypdf2.lower():
            nomes_pdfs_com_palavra_chave_pypdf2.append((arquivo, caminho_pdf))

    # Usar ThreadPoolExecutor para processar arquivos em paralelo
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_file = {}
        for pasta_raiz, sub_pastas, arquivos in os.walk(diretorio):
            for arquivo in arquivos:
                if arquivo.endswith('.pdf'):
                    caminho_pdf = os.path.join(pasta_raiz, arquivo)
                    future_to_file[executor.submit(processar_arquivo, arquivo, caminho_pdf)] = (arquivo, caminho_pdf)
        # Esperar todos os futuros terminarem
        for future in future_to_file:
            future.result()

    return nomes_pdfs_com_palavra_chave_ocr, nomes_pdfs_com_palavra_chave_pypdf2

# Abre o arquivo PDF correspondente
def abrir_pdf(evento, caminho_pdf):
    os.startfile(caminho_pdf)

# Busca com a palavra-chave em uma thread separada
def buscar_pdfs():
    threading.Thread(target=executar_busca, daemon=True).start()

# Executa a busca e exibe resultados
def executar_busca():
    botao_buscar.pack_forget() # Esconde o botão "Buscar" ao iniciar a busca
    # Exibe mensagem de processamento
    label_mensagem.config(text="Processando arquivos, aguarde ...")
    palavra_chave = entrada_pesquisa.get()
    resultados_text.delete("1.0", tk.END)
    # Exibe mensagem de erro
    if not palavra_chave:
        messagebox.showerror("Erro", "O campo 'palavra-chave' é obrigatório.")
        botao_buscar.pack(side=tk.LEFT)
        label_mensagem.config(text="")
        return
    
    resultados_ocr, resultados_pypdf2 = encontrar_nomes_pdfs_com_palavra_chave(root_directory, palavra_chave)

    # Exibe resultados da busca com OCR
    if resultados_ocr:
        resultados_text.insert(tk.END, "Resultados encontrados usando processamento de imagens:\n")
        for nome_arquivo, caminho_pdf in resultados_ocr:
            label_pdf = tk.Label(resultados_text, text=nome_arquivo, fg="blue", cursor="hand2")
            label_pdf.bind("<Button-1>", lambda e, path=caminho_pdf: abrir_pdf(e, path))
            resultados_text.window_create(tk.END, window=label_pdf)
            resultados_text.insert(tk.END, "\n")
    else:
        resultados_text.insert(tk.END, "Nenhum resultado encontrado usando processamento de imagens.\n")

    resultados_text.insert(tk.END, "\n")
    
    # Exibe resultados da busca com PyPDF2
    if resultados_pypdf2:
        resultados_text.insert(tk.END, "Resultados encontrados usando processamento de texto:\n")
        for nome_arquivo, caminho_pdf in resultados_pypdf2:
            label_pdf = tk.Label(resultados_text, text=nome_arquivo, fg="blue", cursor="hand2")
            label_pdf.bind("<Button-1>", lambda e, path=caminho_pdf: abrir_pdf(e, path))
            resultados_text.window_create(tk.END, window=label_pdf)
            resultados_text.insert(tk.END, "\n")
    else:
        resultados_text.insert(tk.END, "Nenhum resultado encontrado usando processamento de texto.\n")

    label_mensagem.config(text="")
    botao_buscar.pack(side=tk.LEFT)

# Limita o número de caracteres da entrada de pesquisa
def limitar_caracteres(evento):
    entrada = entrada_pesquisa.get()
    if len(entrada) > 20:
        entrada_pesquisa.delete(20, tk.END)

# Cria a janela principal
janela = tk.Tk()
janela.title("PDF Search")
janela.geometry("640x480")

# Seção de configuração
frame_configuracao = tk.Frame(janela)
frame_configuracao.pack(fill="both", expand=True)

# Configurações
label_configuracao = tk.Label(frame_configuracao, text="Defina as configurações", font=("Arial", 14, "bold"), fg="red")
label_configuracao.pack(pady=10)

# Entrada para o caminho do Tesseract
entrada_tesseract = tk.Entry(frame_configuracao, width=50)
entrada_tesseract.pack(pady=5)
botao_selecionar_tesseract = tk.Button(frame_configuracao, text="Selecionar Tesseract", command=selecionar_tesseract_path)
botao_selecionar_tesseract.pack(pady=5)

# Entrada para o diretório raiz
entrada_root_directory = tk.Entry(frame_configuracao, width=50)
entrada_root_directory.pack(pady=5)
botao_selecionar_root_directory = tk.Button(frame_configuracao, text="Selecionar Diretório", command=selecionar_root_directory)
botao_selecionar_root_directory.pack(pady=5)

# Botão para confirmar as configurações
botao_confirmar_configuracoes = tk.Button(frame_configuracao, text="Confirmar Configurações", command=confirmar_configuracoes)
botao_confirmar_configuracoes.pack(pady=20)

# Seção do PDF Search
frame_pdf_search = tk.Frame(janela)

# Logo centralizada acima da caixa de pesquisa
logo_label = tk.Label(frame_pdf_search, text="pdf Search", font=("Arial", 24, "bold"), fg="red")
logo_label.pack(pady=20)

# Criar um frame para a entrada e o botão
frame_pesquisa = tk.Frame(frame_pdf_search)
frame_pesquisa.pack()

# Caixa de pesquisa centralizada com limite de 20 caracteres
entrada_pesquisa = tk.Entry(frame_pesquisa, width=40, font=("Arial", 14))
entrada_pesquisa.pack(side=tk.LEFT, padx=10)

# Adiciona um evento de teclado para limitar a entrada de pesquisa
entrada_pesquisa.bind("<KeyRelease>", limitar_caracteres)

# Botão "Buscar" ao lado da caixa de pesquisa
botao_buscar = tk.Button(frame_pesquisa, text="Buscar", font=("Arial", 12, "bold"), command=buscar_pdfs)
botao_buscar.pack(side=tk.LEFT)

# Mensagem de processamento de arquivos
label_mensagem = tk.Label(frame_pdf_search, text="", font=("Arial", 12), fg="red")
label_mensagem.pack(pady=5)

# Texto rolável para exibir resultados
resultados_text = scrolledtext.ScrolledText(frame_pdf_search, wrap=tk.WORD, width=60, height=20, font=("Arial", 12))
resultados_text.pack(pady=10)

# Configurações de inicializar e loop principal da janela
carregar_configuracoes()
janela.mainloop()
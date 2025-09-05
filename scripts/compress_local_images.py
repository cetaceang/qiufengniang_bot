import os
from PIL import Image

def compress_local_images_to_png(source_dir, output_dir, max_width=512):
    """
    压缩指定文件夹内的所有图片，并保存为PNG格式。

    :param source_dir: 存放原始图片的文件夹路径。
    :param output_dir: 保存压缩后图片的文件夹路径。
    :param max_width: 图片的最大宽度，超过此宽度的图片会被按比例缩小。
    """
    # --- 检查路径是否存在 ---
    if not os.path.isdir(source_dir):
        print(f"错误：源文件夹路径不存在 -> '{source_dir}'")
        print("请确保路径正确，并且文件夹已创建。")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"已创建输出文件夹: '{output_dir}'")

    print(f"开始处理文件夹 '{source_dir}' 中的图片，将保存为PNG格式...")

    # --- 遍历源文件夹中的所有文件 ---
    for filename in os.listdir(source_dir):
        source_path = os.path.join(source_dir, filename)

        # 确保处理的是文件而不是子文件夹
        if not os.path.isfile(source_path):
            continue

        try:
            # --- 打开图片 ---
            with Image.open(source_path) as img:
                print(f"正在处理: {filename} ({img.width}x{img.height})")

                # --- 缩小尺寸 ---
                if img.width > max_width:
                    ratio = max_width / float(img.width)
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    print(f"  -> 已缩小尺寸至: {img.width}x{img.height}")

                # --- 保存为PNG ---
                # 构建新的文件名和路径
                new_filename = os.path.splitext(filename)[0] + '.png'
                output_path = os.path.join(output_dir, new_filename)
                
                # PNG的 'compress_level' 参数范围是0-9，数值越高压缩率越高，但越慢。
                # 'optimize' 会尝试更多方法来减小文件大小。
                img.save(output_path, 'PNG', optimize=True, compress_level=9)
                print(f"  -> 已压缩并保存至: {output_path}")

        except (IOError, SyntaxError) as e:
            # 如果文件不是有效的图片格式，则跳过
            print(f"跳过非图片文件或无法识别的文件: {filename} ({e})")

    print("\n处理完成！")
    print(f"所有压缩后的图片都已保存在 '{output_dir}' 文件夹中。")

if __name__ == '__main__':
    # --- !!! 请在这里配置你的路径 !!! ---

    # 1. 你的原始图片所在的文件夹路径
    # 例如: r"C:\Users\YourUser\Desktop\MyImages"
    # 注意：路径前的 'r'很重要，可以防止路径中的反斜杠'\'被错误解析。
    SOURCE_FOLDER = r"请在这里填入你的原始图片文件夹路径"

    # 2. 你希望保存压缩后图片的文件夹路径
    # 脚本会自动创建这个文件夹（如果它不存在）
    # 例如: r"C:\Users\YourUser\Desktop\CompressedOutput"
    OUTPUT_FOLDER = r"请在这里填入你的输出文件夹路径"
    
    # --- 运行压缩函数 ---
    compress_local_images_to_png(SOURCE_FOLDER, OUTPUT_FOLDER)
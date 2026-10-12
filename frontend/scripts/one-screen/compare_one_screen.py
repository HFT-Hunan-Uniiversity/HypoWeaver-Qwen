from PIL import Image, ImageDraw, ImageFont
import os
B='/workspace/hw/review/screens'
pairs={'01_项目列表':'01_projects_list','02_总览':'02_overview_full_flow','03_方向':'03_direction','04_文献':'04_literature_landscape','05_候选_逐个':'05_candidates','06_方案_概要':'06_plan','06b_方案_方法与变量':'06b_plan_variables','07b_数据_绑定':'07_data_binding_readiness','08_数据_结果':'08_analysis_results','09_提案':'09_proposal','10_设置':'10_settings'}
font=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',28)
H=900
for new,old in pairs.items():
    a=Image.open(f'{B}/v2r2/{old}_full.png' if os.path.exists(f'{B}/v2r2/{old}_full.png') else f'{B}/v2r2/{old}.png').convert('RGB')
    b=Image.open(f'{B}/one-screen/1440x900/{new}.png').convert('RGB')
    def fit(im):
        s=H/im.height if im.height>H else 1
        w=int(im.width*s); return im.resize((w,int(im.height*s))), s
    # 旧版整页长图按比例缩到 900 高，标注原始高度
    a2,sa=fit(a); b2,_=fit(b)
    aw=max(a2.width,560); W=aw+b2.width+60; out=Image.new('RGB',(W,H+60),'white'); d=ImageDraw.Draw(out)
    out.paste(a2,(20,50)); out.paste(b2,(40+aw,50))
    d.text((20,8),f'v2r2（整页 {a.width}×{a.height}{"，已缩放" if sa<1 else ""}）',fill='black',font=font)
    d.text((40+aw,8),f'one-screen 1440×900',fill='black',font=font)
    out.save(f'{B}/one-screen/compare/{new}.png')
print('ok')
